"""SQLite auto-restore when live DB is unusable."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app.db.sqlite_recovery import (
    ensure_usable_sqlite_path,
    restore_sqlite_from_backup,
    sqlite_core_tables_ok,
)


def _seed_minimal_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK (id = 1), platform_name TEXT);
            INSERT INTO settings (id, platform_name) VALUES (1, 'SUPPIX');
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                role TEXT,
                company_id TEXT,
                twofa_enabled INTEGER DEFAULT 0,
                email TEXT DEFAULT '',
                twofa_secret TEXT DEFAULT ''
            );
            INSERT INTO users (id, username, password_hash, name, role, company_id, twofa_enabled)
            VALUES ('u1', 'admin', 'x', 'Admin', 'superadmin', NULL, 0);
            """
        )


class SqliteRecoveryTests(unittest.TestCase):
    def test_sqlite_core_tables_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "ok.db"
            _seed_minimal_db(db)
            self.assertTrue(sqlite_core_tables_ok(db))

    def test_ensure_usable_restores_from_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "baupass.db"
            live.write_bytes(b"not-a-valid-sqlite-file" * 200)
            backup_dir = Path(tmp) / "backups"
            backup_dir.mkdir()
            good = backup_dir / "db-backup-test.db"
            _seed_minimal_db(good)

            with mock.patch("backend.app.db.sqlite_recovery._backup_candidates") as candidates:
                candidates.return_value = [good]
                result = ensure_usable_sqlite_path(live)

            self.assertEqual(result, live)
            self.assertTrue(sqlite_core_tables_ok(live))

    def test_restore_copies_sidecars_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.db"
            dest = Path(tmp) / "dest.db"
            _seed_minimal_db(src)
            Path(f"{src}-wal").write_text("wal")
            restore_sqlite_from_backup(src, dest)
            self.assertTrue(dest.is_file())
            self.assertTrue(Path(f"{dest}-wal").is_file())

    def test_ensure_usable_bootstraps_when_no_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "baupass.db"
            live.write_bytes(b"not-a-valid-sqlite-file" * 200)

            with mock.patch("backend.app.db.sqlite_recovery._backup_candidates") as candidates:
                candidates.return_value = []
                result = ensure_usable_sqlite_path(live)

            self.assertEqual(result, live)
            self.assertFalse(live.is_file())


if __name__ == "__main__":
    unittest.main()
