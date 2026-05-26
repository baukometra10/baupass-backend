"""
Tests for platform layer (API keys, migration 013 tables).
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.database import MigrationRunner
from backend.app.migrations import ALL_MIGRATIONS
from backend.app.platform.api_platform.api_keys import authenticate_api_key, create_api_key


class PlatformApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        runner = MigrationRunner(conn)
        runner.run(ALL_MIGRATIONS)
        conn.close()

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_api_key_roundtrip(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        created = create_api_key(
            conn,
            company_id=1,
            name="CI Key",
            scopes="read",
            created_by_user_id="usr-test",
        )
        self.assertTrue(created["api_key"].startswith("bp_live_"))
        row = authenticate_api_key(conn, created["api_key"])
        self.assertIsNotNone(row)
        self.assertEqual(row["company_id"], 1)
        conn.close()

    def test_migration_013_tables_exist(self):
        conn = sqlite3.connect(str(self.db_path))
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for name in (
            "platform_events",
            "developer_api_keys",
            "webhook_endpoints",
            "webhook_deliveries",
        ):
            self.assertIn(name, tables)
        conn.close()


if __name__ == "__main__":
    unittest.main()
