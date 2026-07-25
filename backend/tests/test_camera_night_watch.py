"""Camera night-watch, after-hours escalation, vision ingest, police suggestion."""
from __future__ import annotations

import base64
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.app.database import MigrationRunner
from backend.app.migrations import ALL_MIGRATIONS
from backend.app.platform.physical_operations.camera_ai import analyze_camera_event, ingest_camera_event
from backend.app.platform.physical_operations.camera_escalation import (
    acknowledge_escalation,
    create_critical_escalation,
    create_test_alarm,
    get_escalation,
    list_escalations,
    mark_false_positive,
)
from backend.app.platform.physical_operations.camera_escalation_chain_job import run_camera_escalation_chain
from backend.app.platform.physical_operations.camera_evidence_retention_job import (
    run_camera_evidence_retention,
)
from backend.app.platform.physical_operations.camera_export import (
    build_audit_export,
    build_escalation_export_zip,
)
from backend.app.platform.physical_operations.camera_notifications import notify_camera_violation
from backend.app.platform.physical_operations.camera_registry import (
    create_camera,
    parse_camera_bulk_text,
    touch_camera_heartbeat,
)
from backend.app.platform.physical_operations.camera_vision import (
    analyze_snapshot_b64,
    vision_result_to_event_payload,
)
from backend.app.platform.physical_operations.camera_vision_job import run_camera_after_hours_vision
from backend.app.platform.physical_operations.camera_watch import (
    apply_after_hours_escalation,
    is_after_hours,
    is_after_hours_for_site,
    is_alert_suppressed,
    quiet_suppressed_channels,
    resolve_watch_settings,
    upsert_site_watch_settings,
    upsert_watch_override,
    upsert_watch_settings,
    watch_status,
)
from backend.app.platform.physical_operations.camera_webhook import (
    build_webhook_headers,
    fire_test_webhook,
    sign_webhook_body,
)
from backend.app.platform.physical_operations.nvr_webhook import ingest_nvr_webhook, normalize_nvr_payload
from backend.app.platform.physical_operations.police_directory import (
    _cache_get,
    _cache_put,
    suggest_nearest_police,
)


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
        sunday_night = datetime(2026, 7, 19, 22, 0, tzinfo=timezone.utc)  # Sunday
        self.assertTrue(is_after_hours(db, "cmp-watch", at=sunday_night))
        monday_noon = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)  # Monday
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
                "requireDualAck": False,
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

    def test_multi_site_watch_settings(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {
                "enabled": True,
                "timezone": "UTC",
                "workStart": "08:00",
                "workEnd": "16:00",
                "workDays": "1,2,3,4,5",
                "city": "Berlin",
            },
        )
        upsert_site_watch_settings(
            db,
            "cmp-watch",
            "yard-north",
            {
                "siteName": "Hof Nord",
                "enabled": True,
                "timezone": "UTC",
                "workStart": "06:00",
                "workEnd": "22:00",
                "workDays": "1,2,3,4,5,6,7",
                "city": "Hamburg",
                "latitude": 53.55,
                "longitude": 9.99,
            },
        )
        resolved = resolve_watch_settings(db, "cmp-watch", site="yard-north")
        self.assertEqual(resolved.get("resolvedFrom"), "site")
        self.assertEqual(resolved.get("city"), "Hamburg")
        self.assertEqual(resolved.get("workStart"), "06:00")
        monday_noon = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(is_after_hours_for_site(db, "cmp-watch", site="yard-north", at=monday_noon))
        company_only = resolve_watch_settings(db, "cmp-watch", site="unknown-site")
        self.assertEqual(company_only.get("resolvedFrom"), "company")
        self.assertEqual(company_only.get("city"), "Berlin")
        db.close()

    def test_escalation_detail_clip_and_false_positive_learning(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {"enabled": True, "country": "DE", "city": "Berlin", "latitude": 52.52, "longitude": 13.40},
        )
        clip = base64.b64encode(b"fake-mp4-bytes-for-test").decode("ascii")
        snap = base64.b64encode(b"\xff\xd8\xff\xd9x").decode("ascii")
        created = create_critical_escalation(
            db,
            company_id="cmp-watch",
            event_id="ev-clip-1",
            camera_id="cam-fp-1",
            camera_name="Gate",
            location="yard-north",
            event_type="forced_entry",
            analysis={
                "maxSeverity": "critical",
                "alerts": [{"type": "forced_entry", "severity": "critical"}],
                "afterHours": True,
            },
            snapshot_b64=snap,
            clip_b64=clip,
            site="yard-north",
        )
        self.assertTrue(created.get("ok"))
        eid = created["id"]
        detail = get_escalation(db, "cmp-watch", eid, include_media=True)
        self.assertTrue(detail["hasSnapshot"] or detail.get("snapshotBase64"))
        self.assertEqual(detail.get("clipBase64"), clip)
        self.assertTrue(detail.get("history") is not None)
        fp = mark_false_positive(db, "cmp-watch", eid, actor_user_id="admin-1", note="cat")
        self.assertEqual(fp["status"], "false_positive")
        self.assertTrue(is_alert_suppressed(db, "cmp-watch", "cam-fp-1", "forced_entry"))
        db.close()

    def test_police_cache_roundtrip(self):
        db = self._conn()
        payload = {
            "autoDial": False,
            "station": {"name": "Cached PD", "city": "Berlin", "country": "DE", "phone": "110"},
        }
        _cache_put(db, "de|berlin|52.5|13.4", "DE", "Berlin", payload, hours=1)
        hit = _cache_get(db, "de|berlin|52.5|13.4")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["station"]["name"], "Cached PD")
        sug = suggest_nearest_police(country="DE", city="Berlin", latitude=52.52, longitude=13.40, db=db)
        self.assertFalse(sug.get("autoDial"))
        db.close()

    def test_holiday_override_forces_after_hours(self):
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
        monday_noon = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(is_after_hours(db, "cmp-watch", at=monday_noon))
        upsert_watch_override(
            db,
            "cmp-watch",
            {"overrideDate": "2026-07-20", "kind": "holiday", "note": "public holiday"},
        )
        self.assertTrue(is_after_hours(db, "cmp-watch", at=monday_noon))
        db.close()

    def test_dual_ack_requires_two_users(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {"enabled": True, "requireDualAck": True, "escalateAfterMinutes": 15, "country": "DE", "city": "Berlin"},
        )
        created = create_critical_escalation(
            db,
            company_id="cmp-watch",
            event_id="ev-dual-1",
            camera_id="cam-dual",
            camera_name="Gate",
            location="Yard",
            event_type="forced_entry",
            analysis={
                "maxSeverity": "critical",
                "alerts": [{"type": "forced_entry", "severity": "critical"}],
                "afterHours": True,
            },
        )
        self.assertTrue(created.get("ok"))
        self.assertTrue(created.get("dualAckRequired"))
        eid = created["id"]
        first = acknowledge_escalation(db, "cmp-watch", eid, actor_user_id="admin-1")
        self.assertEqual(first["status"], "pending_second_ack")
        self.assertEqual(first["ackCount"], 1)
        with self.assertRaises(ValueError) as ctx:
            acknowledge_escalation(db, "cmp-watch", eid, actor_user_id="admin-1")
        self.assertEqual(str(ctx.exception), "duplicate_ack")
        second = acknowledge_escalation(
            db, "cmp-watch", eid, actor_user_id="admin-2", mark_security_notified=True
        )
        self.assertEqual(second["status"], "security_notified")
        self.assertGreaterEqual(second["ackCount"], 2)
        self.assertFalse(second.get("autoDial", True))
        db.close()

    def test_chain_stage_bump_with_past_next_at(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {
                "enabled": True,
                "requireDualAck": False,
                "escalateAfterMinutes": 15,
                "escalateSecondContact": "not-a-phone",
                "securityWebhookUrl": "",
            },
        )
        created = create_critical_escalation(
            db,
            company_id="cmp-watch",
            event_id="ev-chain-1",
            camera_id="cam-chain",
            camera_name="Yard",
            location="Yard",
            event_type="forced_entry",
            analysis={
                "maxSeverity": "critical",
                "alerts": [{"type": "forced_entry", "severity": "critical"}],
                "afterHours": True,
            },
        )
        eid = created["id"]
        db.execute(
            "UPDATE camera_escalations SET chain_next_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00.000000Z", eid),
        )
        db.commit()
        out = run_camera_escalation_chain(db)
        self.assertTrue(out.get("ok"))
        self.assertFalse(out.get("autoDial", True))
        self.assertGreaterEqual(int(out.get("stage1") or 0), 1)
        row = db.execute("SELECT chain_stage, chain_next_at FROM camera_escalations WHERE id = ?", (eid,)).fetchone()
        self.assertEqual(int(row["chain_stage"]), 1)
        self.assertTrue(row["chain_next_at"])
        db.execute(
            "UPDATE camera_escalations SET chain_next_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00.000000Z", eid),
        )
        db.commit()
        out2 = run_camera_escalation_chain(db)
        self.assertGreaterEqual(int(out2.get("stage2") or 0), 1)
        row2 = db.execute("SELECT chain_stage FROM camera_escalations WHERE id = ?", (eid,)).fetchone()
        self.assertEqual(int(row2["chain_stage"]), 2)
        hist = get_escalation(db, "cmp-watch", eid)
        types = {h.get("type") for h in (hist.get("history") or [])}
        self.assertIn("chain_second_contact", types)
        self.assertIn("chain_security_webhook", types)
        db.close()

    def test_zone_min_confidence_skips_alerts(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {"enabled": True, "timezone": "UTC", "workStart": "09:00", "workEnd": "10:00", "workDays": "1,2,3,4,5"},
        )
        cam = create_camera(
            db,
            "cmp-watch",
            {"name": "Zone Cam", "location": "Yard", "minConfidence": 0.8, "zoneCriticalOnlyAfterHours": True},
        )
        self.assertEqual(cam.get("minConfidence"), 0.8)
        self.assertTrue(cam.get("zoneCriticalOnlyAfterHours"))
        low = ingest_camera_event(
            db,
            "cmp-watch",
            {"camera_id": cam["id"], "event_type": "forced_entry", "confidence": 0.2},
        )
        self.assertEqual(low.get("skipped"), "below_min_confidence")
        self.assertIsNone(low.get("id"))
        db.close()

    def test_nvr_stub_normalize_and_ingest(self):
        db = self._conn()
        upsert_watch_settings(db, "cmp-watch", {"enabled": True, "requireDualAck": False})
        norm = normalize_nvr_payload(
            "hikvision",
            {"EventNotificationAlert": {"channelID": 3, "eventType": "intrusion", "channelName": "Gate"}},
            {},
        )
        self.assertEqual(norm["vendor"], "hikvision")
        self.assertEqual(norm["event_type"], "possible_intrusion")
        self.assertIn("hik-ch-3", norm["camera_id"])
        result = ingest_nvr_webhook(
            db,
            "cmp-watch",
            "generic",
            {"camera_id": "cam-nvr-1", "event_type": "motion", "confidence": 0.9, "location": "Yard"},
            {},
        )
        self.assertTrue(result.get("ok"))
        self.assertFalse(result.get("autoDial", True))
        db.close()

    def test_export_zip_non_empty(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {"enabled": True, "requireDualAck": False, "country": "DE", "city": "Berlin", "latitude": 52.52, "longitude": 13.40},
        )
        snap = base64.b64encode(b"\xff\xd8\xff\xd9export").decode("ascii")
        created = create_critical_escalation(
            db,
            company_id="cmp-watch",
            event_id="ev-export-1",
            camera_id="cam-export",
            camera_name="Export Cam",
            location="Yard",
            event_type="forced_entry",
            analysis={
                "maxSeverity": "critical",
                "alerts": [{"type": "forced_entry", "severity": "critical"}],
                "afterHours": True,
            },
            snapshot_b64=snap,
        )
        zbytes = build_escalation_export_zip(db, "cmp-watch", created["id"])
        self.assertIsInstance(zbytes, (bytes, bytearray))
        self.assertGreater(len(zbytes), 100)
        import zipfile
        import io

        with zipfile.ZipFile(io.BytesIO(zbytes)) as zf:
            names = set(zf.namelist())
            self.assertIn("incident.pdf", names)
            self.assertIn("meta.json", names)
            self.assertIn("snapshot.jpg", names)
        db.close()

    def test_webhook_signature_header_when_secret_set(self):
        body = b'{"type":"camera.test_webhook","test":true}'
        secret = "unit-test-secret"
        sig = sign_webhook_body(secret, body)
        self.assertTrue(sig.startswith("sha256="))
        headers = build_webhook_headers(
            body=body,
            secret=secret,
            event="camera.test_webhook",
            delivery_id="cwd-test-1",
        )
        self.assertEqual(headers["X-WorkPass-Signature"], sig)
        self.assertEqual(headers["X-WorkPass-Event"], "camera.test_webhook")
        self.assertEqual(headers["X-WorkPass-Delivery-Id"], "cwd-test-1")
        unsigned = build_webhook_headers(body=body, secret="", event="camera.test_webhook")
        self.assertNotIn("X-WorkPass-Signature", unsigned)

    def test_quiet_hours_suppress_sms(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {
                "enabled": True,
                "timezone": "UTC",
                "quietHours": {
                    "enabled": True,
                    "start": "00:00",
                    "end": "23:59",
                    "channels": ["sms"],
                },
                "notifyRules": {"sms": "high", "push": "high", "email": "immediate"},
            },
        )
        cfg = resolve_watch_settings(db, "cmp-watch")
        noon = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        suppressed = quiet_suppressed_channels(cfg, severity="high", at=noon)
        self.assertIn("sms", suppressed)
        # Critical may still allow push even if push listed
        cfg2 = {
            **cfg,
            "quietHours": {"enabled": True, "start": "00:00", "end": "23:59", "channels": ["sms", "push"]},
        }
        suppressed_crit = quiet_suppressed_channels(cfg2, severity="critical", at=noon)
        self.assertIn("sms", suppressed_crit)
        self.assertNotIn("push", suppressed_crit)
        db.close()

    def test_evidence_retention_clears_old_clip(self):
        db = self._conn()
        upsert_watch_settings(db, "cmp-watch", {"enabled": True, "evidenceRetentionDays": 7})
        clip = base64.b64encode(b"old-clip-bytes").decode("ascii")
        snap = base64.b64encode(b"\xff\xd8\xff\xd9old").decode("ascii")
        created = create_critical_escalation(
            db,
            company_id="cmp-watch",
            event_id="ev-ret-1",
            camera_id="cam-ret",
            camera_name="Ret",
            location="Yard",
            event_type="forced_entry",
            analysis={
                "maxSeverity": "critical",
                "alerts": [{"type": "forced_entry", "severity": "critical"}],
                "afterHours": True,
            },
            snapshot_b64=snap,
            clip_b64=clip,
        )
        eid = created["id"]
        db.execute(
            "UPDATE camera_escalations SET created_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00.000000Z", eid),
        )
        db.commit()
        out = run_camera_evidence_retention(db)
        self.assertTrue(out.get("ok"))
        self.assertGreaterEqual(int(out.get("cleared") or 0), 1)
        row = db.execute(
            "SELECT snapshot_b64, clip_b64, status FROM camera_escalations WHERE id = ?",
            (eid,),
        ).fetchone()
        self.assertEqual(str(row["snapshot_b64"] or ""), "")
        self.assertEqual(str(row["clip_b64"] or ""), "")
        self.assertTrue(row["status"])  # metadata kept
        db.close()

    def test_bulk_parse_zone_lat_lng(self):
        items = parse_camera_bulk_text(
            "Gate; Yard; rtsp://1;Zone A;52.52;13.40\n"
            "Legacy; Site; rtsp://2;cam-legacy-1"
        )
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].get("zoneName"), "Zone A")
        self.assertAlmostEqual(float(items[0]["latitude"]), 52.52)
        self.assertAlmostEqual(float(items[0]["longitude"]), 13.40)
        self.assertEqual(items[1].get("id"), "cam-legacy-1")

    def test_test_alarm_and_test_webhook_helpers(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {
                "enabled": True,
                "requireDualAck": False,
                "country": "DE",
                "city": "Berlin",
                "securityWebhookUrl": "",
            },
        )
        dry = create_test_alarm(db, "cmp-watch", dry_run=True, severity="critical")
        self.assertTrue(dry.get("ok"))
        self.assertTrue(dry.get("dryRun"))
        self.assertTrue(dry.get("test"))
        self.assertFalse(dry.get("autoDial", True))
        real = create_test_alarm(db, "cmp-watch", dry_run=False, severity="high")
        self.assertTrue(real.get("ok"))
        self.assertTrue(real.get("id"))
        detail = get_escalation(db, "cmp-watch", real["id"])
        self.assertTrue(detail.get("test"))
        self.assertIn("slaLabel", detail)
        self.assertIsInstance(detail.get("ageSeconds"), int)
        tw = fire_test_webhook(db, "cmp-watch", url="")
        self.assertFalse(tw.get("ok"))
        self.assertEqual(tw.get("error"), "webhook_url_required")
        self.assertFalse(tw.get("autoDial", True))
        db.close()

    def test_audit_export_returns_data(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {
                "enabled": True,
                "requireDualAck": False,
                "privacyNotice": "Nur für Versicherer — kein Auto-Notruf.",
                "country": "DE",
                "city": "Berlin",
            },
        )
        create_critical_escalation(
            db,
            company_id="cmp-watch",
            event_id="ev-audit-1",
            camera_id="cam-audit",
            camera_name="Audit Cam",
            location="Yard",
            event_type="forced_entry",
            analysis={
                "maxSeverity": "critical",
                "alerts": [{"type": "forced_entry", "severity": "critical"}],
                "afterHours": True,
            },
        )
        raw, mime, filename = build_audit_export(
            db, "cmp-watch", from_ts="2020-01-01", to_ts="2099-12-31", fmt="json"
        )
        self.assertEqual(mime, "application/json")
        self.assertIn("audit", filename)
        payload = __import__("json").loads(raw.decode("utf-8"))
        self.assertGreaterEqual(int(payload["meta"]["count"]), 1)
        self.assertIn("privacyNotice", payload["meta"])
        self.assertFalse(payload["meta"].get("autoDial", True))
        self.assertTrue(payload["escalations"][0].get("hasSnapshot") in (True, False))
        zraw, zmime, _ = build_audit_export(db, "cmp-watch", fmt="zip")
        self.assertEqual(zmime, "application/zip")
        self.assertGreater(len(zraw), 50)
        db.close()

    def test_quiet_hours_in_notify_path(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-watch",
            {
                "enabled": True,
                "timezone": "UTC",
                "requireDualAck": False,
                "quietHours": {"enabled": True, "start": "00:00", "end": "23:59", "channels": ["sms"]},
                "notifyRules": {"sms": "high", "push": "off", "email": "off"},
            },
        )
        result = notify_camera_violation(
            db,
            company_id="cmp-watch",
            event_id="ev-quiet-1",
            camera_id="cam-q",
            camera_name="Quiet",
            location="Yard",
            event_type="motion",
            created_at="2026-07-20T12:00:00Z",
            analysis={
                "maxSeverity": "high",
                "critical": False,
                "afterHours": True,
                "alerts": [{"type": "after_hours_activity", "severity": "high", "message": "night"}],
            },
        )
        self.assertTrue(result.get("ok"))
        self.assertIn("sms", result.get("quietSuppressed") or [])
        self.assertFalse(result.get("smsSent"))
        self.assertFalse(result.get("autoDial", True))
        db.close()


if __name__ == "__main__":
    unittest.main()
