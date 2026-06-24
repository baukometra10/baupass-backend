"""Handover signature lock metadata and remote sign flow."""
from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch

from backend.app.domains.workers.handover_sign import WorkerHandoverSignService


class WorkerHandoverSignTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE workers (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                first_name TEXT,
                last_name TEXT,
                worker_type TEXT,
                deleted_at TEXT,
                compliance_signature_data TEXT,
                compliance_signature_at TEXT,
                compliance_signature_captured_by TEXT
            );
            CREATE TABLE companies (id TEXT PRIMARY KEY, name TEXT);
            CREATE TABLE settings (id INTEGER PRIMARY KEY, platform_name TEXT);
            CREATE TABLE worker_handover_sign_sessions (
                id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                signature_data TEXT NOT NULL DEFAULT '',
                signed_at TEXT,
                expires_at TEXT NOT NULL,
                created_by_user_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE worker_documents (
                id TEXT PRIMARY KEY,
                worker_id TEXT,
                company_id TEXT,
                doc_type TEXT,
                filename TEXT,
                file_path TEXT,
                file_size INTEGER,
                created_at TEXT,
                expiry_date TEXT
            );
            INSERT INTO companies (id, name) VALUES ('cmp-1', 'Test GmbH');
            INSERT INTO settings (id, platform_name) VALUES (1, 'WorkPass');
            INSERT INTO workers (
                id, company_id, first_name, last_name, worker_type, deleted_at,
                compliance_signature_data, compliance_signature_at, compliance_signature_captured_by
            ) VALUES (
                'w-1', 'cmp-1', 'Max', 'Muster', 'worker', NULL, '', '', ''
            );
            INSERT INTO worker_documents (
                id, worker_id, company_id, doc_type, filename, file_path, file_size, created_at, expiry_date
            ) VALUES
                ('d-1', 'w-1', 'cmp-1', 'personalausweis', 'id.pdf', '/tmp/id.pdf', 1, '2026-01-01T00:00:00', '2030-12-31'),
                ('d-2', 'w-1', 'cmp-1', 'mindestlohnnachweis', 'pay.pdf', '/tmp/pay.pdf', 1, '2026-01-01T00:00:00', '2030-12-31');
            """
        )

    def test_lock_metadata_reports_missing_signature(self):
        from backend.server import get_worker_lock_metadata

        row = self.conn.execute("SELECT * FROM workers WHERE id = 'w-1'").fetchone()
        meta = get_worker_lock_metadata(self.conn, row)
        self.assertEqual(meta.get("lockReasonCode"), "missing_handover_signature")
        self.assertTrue(meta.get("identityBlocked"))

    @patch("backend.app.domains.workers.handover_sign.log_audit")
    def test_remote_sign_saves_signature(self, _audit):
        service = WorkerHandoverSignService(self.conn)
        invite = service.create_sign_invite("w-1", "cmp-1", actor_user_id="admin-1")
        token = invite["token"]
        sig = "data:image/png;base64,iVBORw0KGgo="
        result = service.submit_signature(token, signature_data=sig, consent_accepted=True)
        self.assertTrue(result.get("ok"))
        row = self.conn.execute(
            "SELECT compliance_signature_data FROM workers WHERE id = 'w-1'"
        ).fetchone()
        self.assertTrue(str(row["compliance_signature_data"]).startswith("data:image/png"))

        from backend.server import get_worker_lock_metadata

        worker = self.conn.execute("SELECT * FROM workers WHERE id = 'w-1'").fetchone()
        self.assertEqual(get_worker_lock_metadata(self.conn, worker), {})


if __name__ == "__main__":
    unittest.main()
