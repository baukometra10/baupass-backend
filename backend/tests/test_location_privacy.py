"""GPS privacy: consent, on-duty only, retention, GDPR erasure."""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.app.database import MigrationRunner
from backend.app.migrations import ALL_MIGRATIONS
from backend.app.platform.physical_operations.location_retention_job import run_gps_location_retention
from backend.app.platform.physical_operations.location_trail import maybe_record_location_sample
from backend.app.platform.workforce.location_privacy import (
    allow_store_live_location,
    apply_gdpr_erasure_if_needed,
    erase_worker_location_data,
    grant_location_consent_for_tests,
    grant_location_legal_ack_for_tests,
    has_location_consent,
)
from backend.app.platform.workforce.presence_state import upsert_live_location


class LocationPrivacyTests(unittest.TestCase):
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
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                location_tracking_enabled INTEGER NOT NULL DEFAULT 1,
                location_tracking_legal_ack INTEGER NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO companies (id, name, status)
            VALUES ('cmp-gps', 'GPS Co', 'aktiv');
            CREATE TABLE IF NOT EXISTS data_consents (
                id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                consent_type TEXT NOT NULL,
                granted INTEGER NOT NULL DEFAULT 0,
                granted_at TEXT,
                revoked_at TEXT,
                ip_address TEXT,
                version TEXT NOT NULL DEFAULT '1.0'
            );
            CREATE TABLE IF NOT EXISTS gdpr_requests (
                id TEXT PRIMARY KEY,
                request_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                requester_type TEXT NOT NULL,
                requester_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                worker_id TEXT,
                submitted_at TEXT NOT NULL,
                completed_at TEXT,
                notes TEXT,
                processed_by TEXT
            );
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

    def test_missing_consent_blocks_store(self):
        db = self._conn()
        grant_location_legal_ack_for_tests(db, company_id="cmp-gps")
        db.commit()
        self.assertFalse(has_location_consent(db, "w-gps-1"))
        ok, reason = allow_store_live_location(
            db, worker_id="w-gps-1", company_id="cmp-gps", on_duty=True
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_location_consent")
        db.close()

    def test_off_duty_blocks_even_with_consent(self):
        db = self._conn()
        grant_location_consent_for_tests(db, worker_id="w-gps-1", company_id="cmp-gps")
        grant_location_legal_ack_for_tests(db, company_id="cmp-gps")
        db.commit()
        ok, reason = allow_store_live_location(
            db, worker_id="w-gps-1", company_id="cmp-gps", on_duty=False
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "not_checked_in")
        db.close()

    def test_legal_ack_required_even_with_consent(self):
        db = self._conn()
        grant_location_consent_for_tests(db, worker_id="w-gps-1", company_id="cmp-gps")
        db.commit()
        ok, reason = allow_store_live_location(
            db, worker_id="w-gps-1", company_id="cmp-gps", on_duty=True
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "location_tracking_legal_ack_required")
        db.close()

    def test_consent_and_duty_allow(self):
        db = self._conn()
        grant_location_consent_for_tests(db, worker_id="w-gps-1", company_id="cmp-gps")
        grant_location_legal_ack_for_tests(db, company_id="cmp-gps")
        db.commit()
        ok, reason = allow_store_live_location(
            db, worker_id="w-gps-1", company_id="cmp-gps", on_duty=True
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "")
        db.close()

    def test_gps_purge_deletes_old_samples(self):
        db = self._conn()
        maybe_record_location_sample(
            db,
            worker_id="w-gps-1",
            company_id="cmp-gps",
            lat=52.52,
            lng=13.40,
            at="2019-01-01T00:00:00.000000Z",
            min_interval_seconds=0,
            min_move_meters=0,
        )
        maybe_record_location_sample(
            db,
            worker_id="w-gps-1",
            company_id="cmp-gps",
            lat=52.53,
            lng=13.41,
            at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            min_interval_seconds=0,
            min_move_meters=0,
        )
        db.commit()
        out = run_gps_location_retention(db)
        self.assertTrue(out.get("ok"))
        self.assertGreaterEqual(int(out.get("deleted") or 0), 1)
        left = db.execute(
            "SELECT COUNT(*) AS n FROM worker_location_samples WHERE company_id = ?",
            ("cmp-gps",),
        ).fetchone()["n"]
        self.assertEqual(int(left), 1)
        db.close()

    def test_gdpr_erasure_deletes_trail_and_live(self):
        db = self._conn()
        grant_location_consent_for_tests(db, worker_id="w-gps-1", company_id="cmp-gps")
        upsert_live_location(
            db,
            worker_id="w-gps-1",
            company_id="cmp-gps",
            lat=52.52,
            lng=13.40,
        )
        maybe_record_location_sample(
            db,
            worker_id="w-gps-1",
            company_id="cmp-gps",
            lat=52.52,
            lng=13.40,
            min_interval_seconds=0,
            min_move_meters=0,
        )
        db.commit()
        db.execute(
            """
            INSERT INTO gdpr_requests (
                id, request_type, status, requester_type, requester_id, company_id, worker_id, submitted_at
            ) VALUES ('gdpr-1', 'erasure', 'pending', 'worker', 'w-gps-1', 'cmp-gps', 'w-gps-1', datetime('now'))
            """
        )
        db.commit()
        row = db.execute("SELECT * FROM gdpr_requests WHERE id = 'gdpr-1'").fetchone()
        result = apply_gdpr_erasure_if_needed(db, row)
        db.commit()
        self.assertIsNotNone(result)
        self.assertGreaterEqual(int(result["samplesDeleted"]), 1)
        n = db.execute(
            "SELECT COUNT(*) AS n FROM worker_location_samples WHERE worker_id = 'w-gps-1'"
        ).fetchone()["n"]
        self.assertEqual(int(n), 0)
        live = db.execute(
            "SELECT last_lat FROM worker_presence_state WHERE worker_id = 'w-gps-1'"
        ).fetchone()
        self.assertTrue(live is None or live["last_lat"] is None)
        db.close()

    def test_gdpr_erasure_redacts_chat_location(self):
        db = self._conn()
        db.execute(
            """
            INSERT INTO chat_messages (
                id, thread_id, company_id, worker_id, sender_type, body, created_at
            ) VALUES ('m-1', 't-1', 'cmp-gps', 'w-gps-1', 'worker', '@location|lat=52.5|lng=13.4', datetime('now'))
            """
        )
        db.commit()
        out = erase_worker_location_data(db, company_id="cmp-gps", worker_id="w-gps-1")
        db.commit()
        self.assertGreaterEqual(int(out.get("chatLocationsRedacted") or 0), 1)
        body = db.execute("SELECT body FROM chat_messages WHERE id = 'm-1'").fetchone()["body"]
        self.assertEqual(body, "@location|redacted")
        db.close()


if __name__ == "__main__":
    unittest.main()
