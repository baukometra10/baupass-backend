"""DSGVO face blur: default on, director reveal, legal ack to disable."""
from __future__ import annotations

import base64
import io
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from backend.app.database import MigrationRunner
from backend.app.migrations import ALL_MIGRATIONS
from backend.app.platform.physical_operations.camera_escalation import (
    create_critical_escalation,
    get_escalation,
)
from backend.app.platform.physical_operations.camera_registry import (
    create_camera,
    get_camera_snapshot_b64,
    touch_camera_heartbeat,
)
from backend.app.platform.physical_operations.camera_watch import (
    get_watch_settings,
    upsert_watch_settings,
)
from backend.app.platform.physical_operations.face_privacy import (
    blur_faces_b64,
    can_reveal_faces,
)


def _skin_jpeg_b64() -> str:
    img = Image.new("RGB", (160, 160), (210, 160, 130))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("ascii")


class CameraFacePrivacyTests(unittest.TestCase):
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
            VALUES ('cmp-face', 'Face Privacy Co', 'aktiv');
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

    def test_can_reveal_faces_roles(self):
        self.assertTrue(can_reveal_faces("company-admin"))
        self.assertTrue(can_reveal_faces("superadmin"))
        self.assertFalse(can_reveal_faces("office"))
        self.assertFalse(can_reveal_faces("worker"))
        self.assertFalse(can_reveal_faces(""))

    def test_default_face_blur_enabled(self):
        db = self._conn()
        cfg = get_watch_settings(db, "cmp-face")
        self.assertTrue(cfg.get("faceBlurEnabled"))
        db.close()

    def test_disable_blur_requires_legal_ack(self):
        db = self._conn()
        with self.assertRaises(ValueError) as ctx:
            upsert_watch_settings(db, "cmp-face", {"faceBlurEnabled": False})
        self.assertEqual(str(ctx.exception), "face_blur_legal_ack_required")
        self.assertTrue(get_watch_settings(db, "cmp-face").get("faceBlurEnabled"))
        db.close()

    def test_disable_blur_with_legal_ack(self):
        db = self._conn()
        upsert_watch_settings(
            db,
            "cmp-face",
            {"faceBlurEnabled": False, "faceBlurLegalAck": True},
        )
        self.assertFalse(get_watch_settings(db, "cmp-face").get("faceBlurEnabled"))
        db.close()

    def test_skin_blob_is_blurred(self):
        raw = _skin_jpeg_b64()
        result = blur_faces_b64(raw)
        self.assertTrue(result.get("ok"))
        self.assertGreater(int(result.get("faces") or 0), 0)
        self.assertTrue(result.get("blurredB64"))
        self.assertNotEqual(result.get("blurredB64"), raw)

    def test_heartbeat_stores_public_and_clear(self):
        db = self._conn()
        cam = create_camera(db, "cmp-face", {"name": "Gate", "location": "Yard"})
        raw = _skin_jpeg_b64()
        touch_camera_heartbeat(
            db,
            "cmp-face",
            cam["id"],
            payload={"camera_name": "Gate"},
            snapshot_b64=raw,
        )
        public = get_camera_snapshot_b64(db, "cmp-face", cam["id"], reveal=False)
        clear = get_camera_snapshot_b64(db, "cmp-face", cam["id"], reveal=True)
        self.assertTrue(public)
        self.assertTrue(clear)
        self.assertNotEqual(public, clear)
        row = db.execute(
            "SELECT last_snapshot_clear_b64 FROM site_cameras WHERE id = ?",
            (cam["id"],),
        ).fetchone()
        self.assertTrue(str(row["last_snapshot_clear_b64"] or "").strip())
        db.close()

    def test_escalation_hides_clear_until_reveal(self):
        db = self._conn()
        raw = _skin_jpeg_b64()
        created = create_critical_escalation(
            db,
            company_id="cmp-face",
            event_id="evt-face-1",
            camera_id="cam-gate",
            camera_name="Gate",
            location="Yard",
            event_type="intrusion",
            analysis={"maxSeverity": "critical", "alerts": [{"type": "forced_entry", "severity": "critical"}]},
            snapshot_b64=raw,
            clip_b64="AAAA",
        )
        self.assertTrue(created.get("ok"))
        eid = created["id"]
        listed = get_escalation(db, "cmp-face", eid, include_media=False)
        self.assertTrue(listed.get("hasClearSnapshot"))
        public = get_escalation(db, "cmp-face", eid, include_media=True, reveal=False)
        revealed = get_escalation(db, "cmp-face", eid, include_media=True, reveal=True)
        self.assertTrue(public.get("snapshotBase64"))
        self.assertNotEqual(public.get("snapshotBase64"), revealed.get("snapshotBase64"))
        self.assertFalse(public.get("facesRevealed"))
        self.assertTrue(revealed.get("facesRevealed"))
        self.assertFalse(public.get("clipBase64"))
        self.assertEqual(revealed.get("clipBase64"), "AAAA")
        db.close()

    def test_face_match_requires_legal_ack_and_blur_off(self):
        db = self._conn()
        with self.assertRaises(ValueError) as ctx:
            upsert_watch_settings(db, "cmp-face", {"faceMatchEnabled": True})
        self.assertEqual(str(ctx.exception), "face_match_legal_ack_required")
        with self.assertRaises(ValueError) as ctx:
            upsert_watch_settings(
                db,
                "cmp-face",
                {"faceMatchEnabled": True, "faceMatchLegalAck": True},
            )
        self.assertEqual(str(ctx.exception), "face_match_requires_blur_off")
        upsert_watch_settings(
            db,
            "cmp-face",
            {
                "faceBlurEnabled": False,
                "faceBlurLegalAck": True,
                "faceMatchEnabled": True,
                "faceMatchLegalAck": True,
            },
        )
        cfg = get_watch_settings(db, "cmp-face")
        self.assertFalse(cfg.get("faceBlurEnabled"))
        self.assertTrue(cfg.get("faceMatchEnabled"))
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS workers (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                photo_data TEXT,
                deleted_at TEXT
            )
            """
        )
        db.commit()
        from backend.app.platform.physical_operations.rtsp_bridge import _enrich_face_match

        enabled = _enrich_face_match(db, "cmp-face", {"worker_id": "w-missing"})
        self.assertNotIn(enabled.get("face_match_skipped"), {"face_blur_enabled", "face_match_disabled"})
        upsert_watch_settings(db, "cmp-face", {"faceBlurEnabled": True})
        skipped_blur = _enrich_face_match(db, "cmp-face", {"worker_id": "w-missing"})
        self.assertEqual(skipped_blur.get("face_match_skipped"), "face_blur_enabled")
        db.close()


if __name__ == "__main__":
    unittest.main()
