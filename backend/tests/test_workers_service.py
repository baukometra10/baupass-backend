"""WorkersService — repository-backed core endpoints."""
from __future__ import annotations

import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.domains.workers.service import WorkersService

_VALID_PHOTO = "data:image/png;base64,abc=="


class WorkersServiceTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE companies (
                id TEXT PRIMARY KEY,
                name TEXT,
                deleted_at TEXT
            );
            INSERT INTO companies (id, name, deleted_at) VALUES ('cmp-a', 'Firma A', NULL);
            INSERT INTO companies (id, name, deleted_at) VALUES ('cmp-b', 'Firma B', NULL);
            CREATE TABLE workers (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                subcompany_id TEXT,
                first_name TEXT,
                last_name TEXT,
                insurance_number TEXT,
                worker_type TEXT,
                role TEXT,
                site TEXT,
                valid_until TEXT,
                deleted_at TEXT,
                status TEXT,
                photo_data TEXT,
                badge_id TEXT,
                badge_id_lookup TEXT,
                badge_pin_hash TEXT,
                physical_card_id TEXT,
                visitor_company TEXT,
                visit_purpose TEXT,
                host_name TEXT,
                visit_end_at TEXT,
                contact_email TEXT,
                leave_balance INTEGER,
                compliance_signature_data TEXT,
                compliance_signature_at TEXT,
                compliance_signature_captured_by TEXT,
                id_handover_at TEXT
            );
            CREATE TABLE access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id TEXT,
                direction TEXT,
                gate TEXT,
                timestamp TEXT
            );
            CREATE TABLE subcompanies (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                name TEXT
            );
            CREATE TABLE hce_device_trust (
                id TEXT PRIMARY KEY,
                worker_id TEXT,
                device_id TEXT,
                platform TEXT,
                app_version TEXT,
                status TEXT,
                trust_version INTEGER,
                signature_algo TEXT,
                device_public_key TEXT,
                created_at TEXT,
                last_seen_at TEXT
            );
            CREATE TABLE hce_device_nonces (
                device_id TEXT,
                nonce TEXT
            );
            CREATE TABLE worker_identity_tokens (
                id TEXT PRIMARY KEY,
                worker_id TEXT,
                company_id TEXT,
                token_hash TEXT,
                token_hint TEXT,
                status TEXT,
                issued_at TEXT,
                expires_at TEXT,
                last_used_at TEXT,
                last_device_id TEXT,
                last_source TEXT
            );
            CREATE TABLE worker_documents (
                id TEXT PRIMARY KEY,
                worker_id TEXT,
                company_id TEXT,
                doc_type TEXT,
                filename TEXT,
                file_path TEXT,
                file_size INTEGER,
                source_email_from TEXT,
                source_inbox_id TEXT,
                uploaded_by_user_id TEXT,
                created_at TEXT,
                notes TEXT,
                expiry_date TEXT
            );
            INSERT INTO workers (
                id, company_id, first_name, last_name, status, worker_type, site,
                deleted_at, badge_id, visitor_company, visit_purpose, host_name, visit_end_at
            ) VALUES (
                'wrk-1', 'cmp-a', 'Max', 'Muster', 'aktiv', 'worker', 'Site A', NULL,
                'BP-001', '', '', '', ''
            );
            INSERT INTO workers (
                id, company_id, first_name, last_name, status, worker_type, site,
                deleted_at, badge_id, visitor_company, visit_purpose, host_name, visit_end_at
            ) VALUES (
                'wrk-2', 'cmp-a', 'Gast', 'Besuch', 'aktiv', 'visitor', '', NULL,
                'VS-001', 'Firma X', 'Meeting', 'Host', '2099-12-31T23:59:00'
            );
            """
        )
        self.conn.commit()
        self.svc = WorkersService()

    def test_delete_and_restore_worker(self):
        user = {"role": "superadmin", "company_id": None}
        deleted = self.svc.delete_worker(self.conn, user, "wrk-1")
        self.assertTrue(deleted["body"]["ok"])
        row = self.conn.execute(
            "SELECT deleted_at FROM workers WHERE id = ?", ("wrk-1",)
        ).fetchone()
        self.assertIsNotNone(row["deleted_at"])
        restored = self.svc.restore_worker(self.conn, user, "wrk-1")
        self.assertTrue(restored["body"]["ok"])
        row = self.conn.execute(
            "SELECT deleted_at FROM workers WHERE id = ?", ("wrk-1",)
        ).fetchone()
        self.assertIsNone(row["deleted_at"])

    def test_worker_stats_scoped(self):
        user = {"role": "company-admin", "company_id": "cmp-a"}
        result = self.svc.worker_stats(self.conn, user)
        self.assertEqual(result["body"]["totalWorkers"], 2)

    def test_current_visitors(self):
        user = {"role": "company-admin", "company_id": "cmp-a"}
        result = self.svc.get_current_visitors(self.conn, user)
        self.assertEqual(len(result["body"]), 1)
        self.assertEqual(result["body"][0]["visitor_company"], "Firma X")

    def test_delete_forbidden(self):
        user = {"role": "company-admin", "company_id": "cmp-other"}
        result = self.svc.delete_worker(self.conn, user, "wrk-1")
        self.assertEqual(result["status"], 403)

    @patch("backend.server._persist_worker_compliance_fields")
    @patch.object(WorkersService, "_ensure_worker_doc_dir", return_value=None)
    @patch("backend.server.serialize_worker_record", side_effect=lambda row: {"id": row["id"]})
    def test_create_worker(self, _serialize, _doc_dir, _compliance):
        user = {"role": "company-admin", "company_id": "cmp-a", "id": "usr-1"}
        result = self.svc.create_worker(
            self.conn,
            user,
            {
                "companyId": "cmp-a",
                "firstName": "Anna",
                "lastName": "Neu",
                "badgePin": "1234",
                "photoData": _VALID_PHOTO,
                "complianceSignatureData": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAD0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
            },
        )
        self.assertEqual(result["status"], 201)
        row = self.conn.execute(
            "SELECT first_name, company_id FROM workers WHERE first_name = ?", ("Anna",)
        ).fetchone()
        self.assertEqual(row["company_id"], "cmp-a")

    @patch.object(WorkersService, "_ensure_worker_doc_dir", return_value=None)
    def test_create_worker_requires_signature(self, _doc_dir):
        user = {"role": "company-admin", "company_id": "cmp-a", "id": "usr-1"}
        result = self.svc.create_worker(
            self.conn,
            user,
            {
                "companyId": "cmp-a",
                "firstName": "No",
                "lastName": "Sign",
                "badgePin": "1234",
                "photoData": _VALID_PHOTO,
            },
        )
        self.assertEqual(result["status"], 400)
        self.assertEqual(result["error"]["error"], "compliance_signature_required")

    def test_update_worker_not_found(self):
        user = {"role": "superadmin", "company_id": None}
        result = self.svc.update_worker(
            self.conn, user, "missing", {"photoData": _VALID_PHOTO}
        )
        self.assertEqual(result["status"], 404)

    def test_set_worker_lock(self):
        user = {"role": "turnstile", "company_id": "cmp-a"}
        result = self.svc.set_worker_lock(self.conn, user, "wrk-1", status="gesperrt")
        self.assertEqual(result["body"]["status"], "gesperrt")
        row = self.conn.execute(
            "SELECT status FROM workers WHERE id = ?", ("wrk-1",)
        ).fetchone()
        self.assertEqual(row["status"], "gesperrt")

    def test_reset_worker_pin(self):
        user = {"role": "superadmin", "company_id": None}
        result = self.svc.reset_worker_pin(self.conn, user, "wrk-1", new_pin="5678")
        self.assertTrue(result["body"]["ok"])
        row = self.conn.execute(
            "SELECT badge_pin_hash FROM workers WHERE id = ?", ("wrk-1",)
        ).fetchone()
        self.assertTrue(row["badge_pin_hash"])

    def test_reset_worker_pin_rejects_visitor(self):
        user = {"role": "superadmin", "company_id": None}
        result = self.svc.reset_worker_pin(self.conn, user, "wrk-2", new_pin="5678")
        self.assertEqual(result["status"], 400)
        self.assertEqual(result["error"]["error"], "visitor_no_pin")

    def test_get_compliance_signature(self):
        user = {"role": "company-admin", "company_id": "cmp-a"}
        result = self.svc.get_compliance_signature(self.conn, user, "wrk-1")
        self.assertEqual(result["body"]["workerId"], "wrk-1")

    def test_bulk_update_status(self):
        user = {"role": "superadmin", "company_id": None}
        result = self.svc.bulk_update_status(
            self.conn, user, ids=["wrk-1", "wrk-2"], status="gesperrt"
        )
        self.assertEqual(result["body"]["updated"], 2)

    def test_bulk_delete_workers(self):
        user = {"role": "company-admin", "company_id": "cmp-a"}
        result = self.svc.bulk_delete_workers(
            self.conn, user, ids=["wrk-1", "wrk-missing"]
        )
        self.assertEqual(result["body"]["deleted"], 1)

    @patch("backend.server.company_has_feature", return_value=True)
    @patch("backend.server.get_company_plan", return_value="enterprise")
    def test_list_worker_documents(self, _plan, _feature):
        self.conn.execute(
            """
            INSERT INTO worker_documents
            (id, worker_id, company_id, doc_type, filename, file_path, file_size,
             source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes, expiry_date)
            VALUES ('doc-1', 'wrk-1', 'cmp-a', 'sonstiges', 'a.pdf', 'uploads/a.pdf', 10,
                    '', NULL, 'usr-1', '2026-01-01', '', NULL)
            """
        )
        self.conn.commit()
        user = {"role": "company-admin", "company_id": "cmp-a"}
        result = self.svc.list_worker_documents(self.conn, user, "wrk-1")
        self.assertEqual(len(result["body"]), 1)
        self.assertEqual(result["body"][0]["id"], "doc-1")

    @patch("backend.server.unlock_worker_if_documents_valid")
    @patch("backend.server.company_has_feature", return_value=True)
    @patch("backend.server.get_company_plan", return_value="enterprise")
    def test_upload_worker_document(self, _plan, _feature, _unlock):
        user = {"role": "company-admin", "company_id": "cmp-a", "id": "usr-1"}
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "documents"
            with patch("backend.server.DOCS_UPLOAD_DIR", docs_dir), patch(
                "backend.server.BASE_DIR", Path(tmp)
            ), patch("backend.server._stored_file_path", side_effect=lambda p: str(p.relative_to(tmp))):
                result = self.svc.upload_worker_document(
                    self.conn,
                    user,
                    "wrk-1",
                    doc_type_raw="sonstiges",
                    notes_raw="note",
                    expiry_date_raw="",
                    filename="test.pdf",
                    mimetype="application/pdf",
                    file_data=b"%PDF-1.4",
                )
        self.assertTrue(result["body"]["ok"])
        row = self.conn.execute(
            "SELECT doc_type, filename FROM worker_documents WHERE worker_id = ?",
            ("wrk-1",),
        ).fetchone()
        self.assertEqual(row["doc_type"], "sonstiges")

    @patch("backend.server.company_has_feature", return_value=True)
    @patch("backend.server.get_company_plan", return_value="enterprise")
    def test_delete_worker_document(self, _plan, _feature):
        self.conn.execute(
            """
            INSERT INTO worker_documents
            (id, worker_id, company_id, doc_type, filename, file_path, file_size,
             source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes, expiry_date)
            VALUES ('doc-del', 'wrk-1', 'cmp-a', 'sonstiges', 'gone.pdf', 'gone.pdf', 1,
                    '', NULL, 'usr-1', '2026-01-01', '', NULL)
            """
        )
        self.conn.commit()
        user = {"role": "superadmin", "company_id": None}
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "gone.pdf"
            file_path.write_bytes(b"x")
            with patch("backend.server.BASE_DIR", Path(tmp)):
                result = self.svc.delete_worker_document(
                    self.conn, user, "wrk-1", "doc-del"
                )
        self.assertTrue(result["body"]["ok"])
        count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM worker_documents WHERE id = ?", ("doc-del",)
        ).fetchone()["c"]
        self.assertEqual(count, 0)

    def test_list_worker_documents_forbidden(self):
        user = {"role": "company-admin", "company_id": "cmp-other"}
        result = self.svc.list_worker_documents(self.conn, user, "wrk-1")
        self.assertEqual(result["status"], 403)

    def test_import_workers_csv(self):
        csv_text = (
            "vorname,nachname,firma,typ\n"
            "Erika,Muster,Firma A,worker\n"
            "Hans,Test,,worker\n"
        ).encode("utf-8")
        user = {"role": "company-admin", "company_id": "cmp-a", "id": "usr-1"}
        result = self.svc.import_workers_csv(self.conn, user, csv_text)
        self.assertEqual(result["body"]["created"], 2)
        count = self.conn.execute("SELECT COUNT(*) AS c FROM workers").fetchone()["c"]
        self.assertEqual(count, 4)

    @patch("backend.server.visible_worker_clause", return_value=(" WHERE workers.company_id = ?", ["cmp-a"]))
    def test_export_workers_csv(self, _clause):
        user = {"role": "company-admin", "company_id": "cmp-a"}
        result = self.svc.export_workers_csv(self.conn, user, include_deleted=False)
        data = result["response"]["data"].decode("utf-8-sig")
        self.assertIn("first_name", data)
        self.assertIn("Max", data)

    @patch("backend.server.visible_worker_clause", return_value=(" WHERE workers.company_id = ?", ["cmp-a"]))
    def test_export_workers_signatures_zip(self, _clause):
        import zipfile

        self.conn.execute(
            "UPDATE workers SET compliance_signature_data = ? WHERE id = 'wrk-1'",
            ("data:image/png;base64,iVBORw0KGgo=",),
        )
        self.conn.commit()
        user = {"role": "company-admin", "company_id": "cmp-a"}
        result = self.svc.export_workers_signatures_zip(self.conn, user, include_deleted=False)
        self.assertIn("response", result)
        with zipfile.ZipFile(io.BytesIO(result["response"]["data"])) as archive:
            names = archive.namelist()
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].endswith(".png"))

    @patch("backend.server.visible_worker_clause", return_value=(" WHERE workers.company_id = ?", ["cmp-a"]))
    def test_export_workers_signatures_zip_empty(self, _clause):
        user = {"role": "company-admin", "company_id": "cmp-a"}
        result = self.svc.export_workers_signatures_zip(self.conn, user, include_deleted=False)
        self.assertEqual(result["status"], 404)
        self.assertEqual(result["error"]["error"], "no_signatures")

    def test_import_workers_csv_invalid_empty(self):
        user = {"role": "superadmin", "company_id": None}
        result = self.svc.import_workers_csv(self.conn, user, b"")
        self.assertEqual(result["status"], 400)

    def test_list_hce_devices(self):
        self.conn.execute(
            """
            INSERT INTO hce_device_trust
            (id, worker_id, device_id, platform, app_version, status, trust_version,
             signature_algo, device_public_key, created_at, last_seen_at)
            VALUES ('hce-1', 'wrk-1', 'dev-abc', 'android', '1.0', 'active', 1,
                    'ed25519', 'pk', '2026-01-01', '2026-01-02')
            """
        )
        self.conn.commit()
        user = {"role": "company-admin", "company_id": "cmp-a"}
        result = self.svc.list_hce_devices(self.conn, user, "wrk-1")
        self.assertEqual(len(result["body"]["devices"]), 1)
        self.assertEqual(result["body"]["devices"][0]["deviceId"], "dev-abc")

    @patch("backend.server.issue_worker_identity_token")
    def test_create_identity_token(self, mock_issue):
        mock_issue.return_value = {
            "created": True,
            "rotated": False,
            "token": "tok-secret",
            "status": "active",
            "tokenHint": "secret",
            "issuedAt": "2026-01-01",
            "expiresAt": "2027-01-01",
            "lastUsedAt": "",
        }
        user = {"role": "superadmin", "company_id": None, "id": "usr-1"}
        result = self.svc.create_or_rotate_worker_identity_token(
            self.conn, user, "wrk-1", rotate=False
        )
        self.assertTrue(result["body"]["created"])
        mock_issue.assert_called_once()

    def test_get_identity_token_unconfigured(self):
        user = {"role": "company-admin", "company_id": "cmp-a"}
        result = self.svc.get_worker_identity_token(self.conn, user, "wrk-1")
        self.assertFalse(result["body"]["configured"])


if __name__ == "__main__":
    unittest.main()
