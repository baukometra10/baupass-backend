"""GDPR Art. 15 access package."""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.database import MigrationRunner
from backend.app.migrations import ALL_MIGRATIONS
from backend.app.platform.workforce.gdpr_package import apply_gdpr_access_if_needed, build_access_export
from backend.app.platform.workforce.location_privacy import grant_location_consent_for_tests


class GdprPackageTests(unittest.TestCase):
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
            INSERT OR IGNORE INTO companies (id, name, status)
            VALUES ('cmp-gdpr', 'GDPR Co', 'aktiv');
            CREATE TABLE IF NOT EXISTS workers (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                status TEXT
            );
            INSERT OR IGNORE INTO workers (id, company_id, first_name, last_name, status)
            VALUES ('w-gdpr-1', 'cmp-gdpr', 'Ada', 'Muster', 'aktiv');
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

    def test_access_export_includes_profile_and_consents(self):
        db = self._conn()
        grant_location_consent_for_tests(db, worker_id="w-gdpr-1", company_id="cmp-gdpr")
        db.commit()
        package = build_access_export(db, company_id="cmp-gdpr", worker_id="w-gdpr-1")
        self.assertTrue(package.get("ok"))
        self.assertEqual(package.get("profile", {}).get("first_name") or package.get("profile", {}).get("id"), "Ada" if package.get("profile", {}).get("first_name") else "w-gdpr-1")
        self.assertTrue(package.get("consents"))
        db.execute(
            """
            INSERT INTO gdpr_requests (
                id, request_type, status, requester_type, requester_id, company_id, worker_id, submitted_at
            ) VALUES ('gdpr-a1', 'access', 'pending', 'worker', 'w-gdpr-1', 'cmp-gdpr', 'w-gdpr-1', datetime('now'))
            """
        )
        db.commit()
        row = db.execute("SELECT * FROM gdpr_requests WHERE id = 'gdpr-a1'").fetchone()
        access = apply_gdpr_access_if_needed(db, row)
        self.assertIsNotNone(access)
        db.close()


if __name__ == "__main__":
    unittest.main()
