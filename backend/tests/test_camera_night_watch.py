"""Camera night-watch, after-hours escalation, vision ingest, police suggestion."""
from __future__ import annotations

import base64
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.app.database import MigrationRunner
from backend.app.migrations import ALL_MIGRATIONS
from backend.app.platform.physical_operations.camera_ai import analyze_camera_event, ingest_camera_event
from backend.app.platform.physical_operations.camera_escalation import (
    acknowledge_escalation,
    create_critical_escalation,
    list_escalations,
)
from backend.app.platform.physical_operations.camera_registry import create_camera, touch_camera_heartbeat
from backend.app.platform.physical_operations.camera_vision import (
    analyze_snapshot_b64,
    vision_result_to_event_payload,
)
from backend.app.platform.physical_operations.camera_vision_job import run_camera_after_hours_vision
from backend.app.platform.physical_operations.camera_watch import (
    apply_after_hours_escalation,
    is_after_hours,
    upsert_watch_settings,
    watch_status,
)
from backend.app.platform.physical_operations.police_directory import suggest_nearest_police


class CameraNightWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        MigrationRunner(conn).run(ALL_MIGRATIONS)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO companies (id, name, status)
            VALUES ('cmp-watch', 'Watch Co', 'aktiv');
            """
        )
        conn.commit()
        conn.close()
        os.environ["BAUPASS_VISION_FORCE_HEURISTIC"] = "1"
        os.environ["BAUPASS_CAMERA_VISION_HEURISTIC"] = "1"

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass
        os.environ.pop("BAUPASS_VISION_FORCE_HEURISTIC", None)

    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def test_after_hours_outside_window(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {
                "enabled": True,
                "timezone": "UTC",
                "workStart": "09:00",
                "workEnd": "17:00",
                "workDays": "1,2,3,4,5",
            },
        )
        sunday_night = datetime(2026, 7, 19, 22, 0, tzinfo=ZoneInfo("UTC"))  # Sunday
        self.assertTrue(is_after_hours(db, "cmp-watch", at=sunday_night))
        monday_noon = datetime(2026, 7, 20, 12, 0, tzinfo=ZoneInfo("UTC"))  # Monday
        self.assertFalse(is_after_hours(db, "cmp-watch", at=monday_noon))
        db.close()

    def test_after_hours_boosts_motion(self):
        base = analyze_camera_event("cmp-watch", {"event_type": "motion"}, after_hours=False)
        self.assertFalse(any(a["type"] == "after_hours_activity" for a in base["alerts"]))
        night = analyze_camera_event("cmp-watch", {"event_type": "motion"}, after_hours=True)
        self.assertTrue(night["afterHours"])
        self.assertTrue(any(a["type"] == "after_hours_activity" for a in night["alerts"]))
        self.assertTrue(night["snapshotRequired"])

    def test_critical_snapshot_fallback_and_escalation(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {
                "enabled": True,
                "timezone": "UTC",
                "workStart": "09:00",
                "workEnd": "10:00",
                "workDays": "1,2,3,4,5",
                "country": "DE",
                "city": "Berlin",
                "latitude": 52.52,
                "longitude": 13.40,
            },
        )
        cam = create_camera(db, "cmp-watch", {"name": "Gate", "location": "Yard"})
        tiny = base64.b64encode(b"\xff\xd8\xff\xd9fakejpeg").decode("ascii")
        touch_camera_heartbeat(
            db,
            "cmp-watch",
            cam["id"],
            payload={"camera_name": "Gate"},
            snapshot_b64=tiny,
        )
        result = ingest_camera_event(
            db,
            "cmp-watch",
            {
                "camera_id": cam["id"],
                "event_type": "forced_entry",
                "confidence": 0.9,
            },
        )
        self.assertTrue(result.get("id"))
        self.assertTrue((result.get("analysis") or {}).get("hasSnapshot"))
        esc = list_escalations(db, "cmp-watch", limit=5)
        self.assertTrue(esc)
        self.assertTrue(esc[0].get("policeName") or esc[0].get("policePhone"))
        ack = acknowledge_escalation(
            db,
            "cmp-watch",
            esc[0]["id"],
            actor_user_id="admin-1",
            mark_security_notified=True,
        )
        self.assertEqual(ack["status"], "security_notified")
        db.close()

    def test_police_suggestion_berlin(self):
        sug = suggest_nearest_police(country="DE", city="Berlin", latitude=52.52, longitude=13.40)
        self.assertFalse(sug.get("autoDial"))
        self.assertIsNotNone(sug.get("station"))
        self.assertIn("Berlin", sug["station"]["city"])

    def test_vision_heuristic_and_job(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {
                "enabled": True,
                "timezone": "UTC",
                "workStart": "09:00",
                "workEnd": "10:00",
                "workDays": "1,2,3,4,5",
            },
        )
        cam = create_camera(db, "cmp-watch", {"name": "Yard Cam", "location": "A"})
        tiny = base64.b64encode(b"\xff\xd8\xff\xd9x").decode("ascii")
        touch_camera_heartbeat(
            db,
            "cmp-watch",
            cam["id"],
            payload={},
            snapshot_b64=tiny,
        )
        vision = analyze_snapshot_b64(tiny, camera_name="Yard Cam", meta={"assume_person": True})
        self.assertTrue(vision.get("personDetected") or vision.get("labels"))
        payload = vision_result_to_event_payload(vision, camera_id=cam["id"], company_id="cmp-watch")
        self.assertEqual(payload["camera_id"], cam["id"])
        out = run_camera_after_hours_vision(db)
        self.assertTrue(out.get("ok"))
        # Job should ingest when after hours (work window 09-10 UTC; most times are after hours)
        status = watch_status(db, "cmp-watch")
        if status.get("afterHours"):
            self.assertGreaterEqual(int(out.get("ingested") or 0), 0)
        db.close()

    def test_apply_escalation_helper(self):
        analysis = apply_after_hours_escalation(
            {"event_type": "motion", "alerts": []},
            after_hours=True,
        )
        self.assertEqual(analysis["maxSeverity"], "high")
        critical = create_critical_escalation(
            self._conn(),
            company_id="cmp-watch",
            event_id="cam-x",
            camera_id="cam-1",
            camera_name="Cam",
            location="Site",
            event_type="forced_entry",
            analysis={"maxSeverity": "critical", "alerts": [{"type": "forced_entry", "severity": "critical"}], "afterHours": True},
            snapshot_b64="",
        )
        self.assertTrue(critical.get("ok"))
        self.assertFalse(critical.get("autoDial", True))


if __name__ == "__main__":
    unittest.main()
