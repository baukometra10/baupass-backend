"""Tests for site camera registry and AI ingest."""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.database import MigrationRunner
from backend.app.migrations import ALL_MIGRATIONS
from backend.app.platform.physical_operations.camera_ai import analyze_camera_event, ingest_camera_event
from backend.app.platform.physical_operations.camera_registry import (
    bulk_create_cameras,
    create_camera,
    list_cameras,
    parse_camera_bulk_text,
    touch_camera_heartbeat,
)


class CameraRegistryTests(unittest.TestCase):
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
            VALUES ('cmp-cam-test', 'Camera Test Co', 'aktiv');
            """
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def test_create_and_heartbeat(self):
        db = self._conn()
        cam = create_camera(db, "cmp-cam-test", {"name": "Gate North", "location": "Site A"})
        self.assertEqual(cam["name"], "Gate North")
        touch_camera_heartbeat(db, "cmp-cam-test", cam["id"], payload={"camera_name": "Gate North"})
        rows = list_cameras(db, "cmp-cam-test")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["online"])
        db.close()

    def test_analyze_ppe_violation(self):
        analysis = analyze_camera_event(
            "cmp-cam-test",
            {"event_type": "ppe_check", "ppe": False, "camera_id": "cam-1"},
        )
        self.assertTrue(analysis["alerts"])
        self.assertEqual(analysis["ppe_compliant"], 0)

    def test_ingest_heartbeat_only(self):
        db = self._conn()
        result = ingest_camera_event(
            db,
            "cmp-cam-test",
            {"camera_id": "hb-cam", "heartbeat": True, "camera_name": "HB Cam"},
        )
        self.assertTrue(result.get("heartbeat"))
        cams = list_cameras(db, "cmp-cam-test")
        self.assertIn("hb-cam", [c["id"] for c in cams])
        db.close()

    def test_bulk_import_text(self):
        db = self._conn()
        text = "Cam A; Site 1; rtsp://10.0.0.1/s\nCam B, Site 2, rtsp://10.0.0.2/s"
        items = parse_camera_bulk_text(text)
        self.assertEqual(len(items), 2)
        result = bulk_create_cameras(db, "cmp-cam-test", items)
        self.assertEqual(result["created"], 2)
        rows = list_cameras(db, "cmp-cam-test")
        self.assertEqual(len(rows), 2)
        db.close()

    def test_bulk_duplicate_names_get_unique_ids(self):
        db = self._conn()
        items = parse_camera_bulk_text("Tor Nord; Site A; rtsp://1\nTor Nord; Site B; rtsp://2")
        result = bulk_create_cameras(db, "cmp-cam-test", items)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result.get("updated", 0), 0)
        ids = [c["id"] for c in result["cameras"]]
        self.assertEqual(len(set(ids)), 2)
        db.close()


if __name__ == "__main__":
    unittest.main()
