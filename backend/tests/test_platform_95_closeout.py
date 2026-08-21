"""Tests for Platform ≥95 closeout modules (HA posture, privacy gate, integrations)."""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class HaPostureTests(unittest.TestCase):
    def test_sqlite_single_node_score(self):
        from backend.app.platform.ha.posture import collect_ha_posture

        with mock.patch("backend.app.db.runtime.postgres_runtime_enabled", return_value=False), mock.patch(
            "backend.app.tasks.task_queues_ready", return_value=False
        ):
            with mock.patch.dict(os.environ, {"REDIS_URL": "", "SUPPIX_WEB_REPLICAS": "1"}, clear=False):
                ha = collect_ha_posture()
        self.assertEqual(ha["level"], "sqlite_single_node")
        self.assertTrue(ha["checks"]["sqliteReplicaUnsafe"])
        self.assertLess(ha["score"], 50)

    def test_ha_production_score_when_flags_set(self):
        from backend.app.platform.ha.posture import collect_ha_posture

        env = {
            "REDIS_URL": "redis://localhost:6379/0",
            "SUPPIX_EMBED_RQ_WORKER": "0",
            "SUPPIX_WEB_REPLICAS": "2",
            "UPLOAD_BACKEND": "s3",
            "S3_BUCKET": "baupass-media",
            "SUPPIX_PG_REQUIRED": "1",
        }
        with mock.patch("backend.app.db.runtime.postgres_runtime_enabled", return_value=True), mock.patch(
            "backend.app.tasks.task_queues_ready", return_value=True
        ):
            with mock.patch.dict(os.environ, env, clear=False):
                ha = collect_ha_posture()
        self.assertGreaterEqual(ha["score"], 95)
        self.assertEqual(ha["level"], "ha_production")
        self.assertFalse(ha["checks"]["sqliteReplicaUnsafe"])


class CameraLegalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = sqlite3.connect(self.tmp.name)
        self.db.row_factory = sqlite3.Row

    def tearDown(self):
        self.db.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_gate_blocks_until_ack(self):
        from backend.app.platform.physical_operations.camera_legal import allow_camera_evidence, set_camera_legal

        ok, reason = allow_camera_evidence(self.db, "c1")
        self.assertFalse(ok)
        self.assertEqual(reason, "camera_recording_legal_ack_required")
        set_camera_legal(
            self.db,
            "c1",
            recording_enabled=True,
            legal_ack=True,
            actor="admin@test",
            legal_basis_text="Betriebsrat OK 2026",
            valid_until="2099-01-01T00:00:00Z",
        )
        ok2, reason2 = allow_camera_evidence(self.db, "c1")
        self.assertTrue(ok2)
        self.assertIsNone(reason2)

    def test_rejects_missing_basis_and_bad_until(self):
        from backend.app.platform.physical_operations.camera_legal import set_camera_legal

        bad_basis = set_camera_legal(
            self.db,
            "c1",
            recording_enabled=True,
            legal_ack=True,
            actor="a",
            legal_basis_text="short",
        )
        self.assertEqual(bad_basis.get("error"), "legal_basis_text_required")
        bad_until = set_camera_legal(
            self.db,
            "c1",
            recording_enabled=True,
            legal_ack=True,
            actor="a",
            legal_basis_text="Betriebsrat documented OK",
            valid_until="not-a-date",
        )
        self.assertEqual(bad_until.get("error"), "camera_recording_legal_ack_invalid_until")


class OutboundUrlSafetyTests(unittest.TestCase):
    def test_blocks_localhost_and_private(self):
        from backend.app.platform.security.outbound_url import assert_safe_outbound_url

        self.assertFalse(assert_safe_outbound_url("http://example.com").get("ok"))
        self.assertFalse(assert_safe_outbound_url("https://127.0.0.1/hook").get("ok"))
        self.assertFalse(assert_safe_outbound_url("https://10.0.0.5/x").get("ok"))
        self.assertFalse(assert_safe_outbound_url("https://localhost/hook").get("ok"))
        self.assertTrue(assert_safe_outbound_url("https://hooks.zapier.com/hooks/catch/1").get("ok"))


class LegalHoldEraseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = sqlite3.connect(self.tmp.name)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE legal_holds (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_by TEXT,
                created_at TEXT NOT NULL,
                released_at TEXT
            );
            CREATE TABLE worker_location_samples (
                id INTEGER PRIMARY KEY,
                worker_id TEXT,
                company_id TEXT
            );
            INSERT INTO worker_location_samples(worker_id, company_id) VALUES ('w1', 'c1');
            INSERT INTO legal_holds(id, company_id, target_type, target_id, reason, active, created_at)
            VALUES ('lh1', 'c1', 'company', 'c1', 'hold', 1, '2026-01-01');
            """
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_erase_blocked_by_legal_hold(self):
        from backend.app.platform.workforce.location_privacy import erase_worker_location_data

        out = erase_worker_location_data(self.db, company_id="c1", worker_id="w1")
        self.assertTrue(out.get("blockedByLegalHold"))
        self.assertEqual(out.get("samplesDeleted"), 0)


class PersonioZapierPartnerTests(unittest.TestCase):
    def test_personio_map_and_preview_sample(self):
        from backend.app.platform.enterprise.personio import map_personio_employee, sync_personio_preview

        mapped = map_personio_employee(
            {"id": 9, "attributes": {"email": {"value": "x@y.z"}, "first_name": {"value": "A"}, "last_name": {"value": "B"}}}
        )
        self.assertEqual(mapped["email"], "x@y.z")
        preview = sync_personio_preview({"dry_run_sample": True})
        self.assertTrue(preview.get("ok"))
        self.assertGreaterEqual(len(preview.get("employees") or []), 1)

    def test_personio_writeback_upsert(self):
        from backend.app.platform.enterprise.personio import upsert_personio_workers

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = sqlite3.connect(tmp.name)
        db.row_factory = sqlite3.Row
        db.execute(
            """
            CREATE TABLE workers (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                first_name TEXT,
                last_name TEXT,
                contact_email TEXT,
                status TEXT,
                role TEXT,
                site TEXT,
                valid_until TEXT,
                photo_data TEXT,
                badge_id TEXT,
                deleted_at TEXT,
                updated_at TEXT
            )
            """
        )
        db.commit()
        first = upsert_personio_workers(
            db,
            "c1",
            [{"email": "ada@example.com", "firstName": "Ada", "lastName": "Lovelace", "externalId": "1"}],
        )
        second = upsert_personio_workers(
            db,
            "c1",
            [{"email": "ada@example.com", "firstName": "Ada", "lastName": "L.", "externalId": "1"}],
        )
        self.assertEqual(first.get("created"), 1)
        self.assertEqual(second.get("updated"), 1)
        count = db.execute("SELECT COUNT(*) AS c FROM workers").fetchone()["c"]
        self.assertEqual(count, 1)
        db.close()
        Path(tmp.name).unlink(missing_ok=True)

    def test_personio_absence_conflict_keeps_local(self):
        from backend.app.platform.enterprise.personio import upsert_personio_absences

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = sqlite3.connect(tmp.name)
        db.row_factory = sqlite3.Row
        db.executescript(
            """
            CREATE TABLE workers (
                id TEXT PRIMARY KEY, company_id TEXT, first_name TEXT, last_name TEXT,
                contact_email TEXT, status TEXT, role TEXT, site TEXT, valid_until TEXT,
                photo_data TEXT, badge_id TEXT, deleted_at TEXT
            );
            CREATE TABLE leave_requests (
                id TEXT PRIMARY KEY, worker_id TEXT, company_id TEXT, type TEXT,
                start_date TEXT, end_date TEXT, days_count INTEGER, note TEXT,
                status TEXT, created_at TEXT
            );
            INSERT INTO workers VALUES ('w1','c1','A','B','a@b.c','aktiv','worker','','','','PN-9',NULL);
            INSERT INTO leave_requests VALUES (
                'lr1','w1','c1','urlaub','2026-08-01','2026-08-05',5,'personio:abs1','genehmigt','2026-01-01T00:00:00Z'
            );
            """
        )
        db.commit()
        result = upsert_personio_absences(
            db,
            "c1",
            [
                {
                    "externalId": "abs1",
                    "employeeExternalId": "9",
                    "startDate": "2026-08-01",
                    "endDate": "2026-08-05",
                    "status": "abgelehnt",
                    "type": "urlaub",
                }
            ],
        )
        self.assertEqual(len(result.get("conflicts") or []), 1)
        status = db.execute("SELECT status FROM leave_requests WHERE id = 'lr1'").fetchone()["status"]
        self.assertEqual(status, "genehmigt")
        db.close()
        Path(tmp.name).unlink(missing_ok=True)

    def test_encrypt_text_aliases_roundtrip(self):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode("ascii")
        with mock.patch.dict(os.environ, {"BAUPASS_FIELD_ENCRYPTION_KEY": key}, clear=False):
            # Reset cached fernet
            import backend.app.platform.security.field_encryption as fe

            fe._fernet = False
            enc = fe.encrypt_text("secret-token")
            self.assertTrue(str(enc).startswith("enc:v1:"))
            self.assertEqual(fe.decrypt_text(enc), "secret-token")
            fe._fernet = False

    def test_ipaas_catalog_and_sign(self):
        from backend.app.platform.enterprise.zapier_make import ipaas_catalog, sign_payload

        cat = ipaas_catalog()
        self.assertTrue(cat["triggers"])
        self.assertEqual(sign_payload("secret", b"{}"), sign_payload("secret", b"{}"))

    def test_partner_packages(self):
        from backend.app.platform.enterprise.partner_cert import build_elster_package, partner_readiness_summary

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = sqlite3.connect(tmp.name)
        db.row_factory = sqlite3.Row
        db.execute(
            "CREATE TABLE workers (id TEXT, company_id TEXT, deleted_at TEXT)"
        )
        db.commit()
        pkg = build_elster_package(db, "c1", tax_year="2026")
        self.assertEqual(pkg["program"], "elster")
        self.assertFalse(pkg["certified"])
        summary = partner_readiness_summary(db, "c1")
        self.assertFalse(summary["officiallyCertified"])
        db.close()
        Path(tmp.name).unlink(missing_ok=True)

    def test_datev_oauth_state_csrf(self):
        from backend.app.platform.auth.sso_state import consume_datev_state, issue_datev_state

        state = issue_datev_state("cmp-1")
        self.assertTrue(state.startswith("cmp-1:"))
        self.assertEqual(consume_datev_state(state), "cmp-1")
        self.assertIsNone(consume_datev_state(state))
        self.assertIsNone(consume_datev_state("cmp-1:forged"))


class ErpDeltaTests(unittest.TestCase):
    def test_idempotent_replay(self):
        from backend.app.platform.enterprise.erp_adapters import sync_erp_delta

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = sqlite3.connect(tmp.name)
        db.row_factory = sqlite3.Row
        with mock.patch(
            "backend.app.platform.enterprise.erp_adapters.sap_export_preview",
            return_value={"period": "2026-08", "rows": [{"workerId": "1", "hours": 8}]},
        ), mock.patch(
            "backend.app.platform.enterprise.erp_adapters.push_erp_export",
            return_value={"ok": True, "rowCount": 1},
        ):
            first = sync_erp_delta(db, "c1", "sap", {"dry_run": True}, idempotency_key="")
            second = sync_erp_delta(db, "c1", "sap", {"dry_run": True}, idempotency_key="")
            # Content change must mint a new key (not replay).
            with mock.patch(
                "backend.app.platform.enterprise.erp_adapters.sap_export_preview",
                return_value={"period": "2026-08", "rows": [{"workerId": "1", "hours": 9}]},
            ):
                third = sync_erp_delta(db, "c1", "sap", {"dry_run": True}, idempotency_key="")
        self.assertTrue(first.get("ok"))
        self.assertTrue(second.get("idempotentReplay"))
        self.assertNotEqual(first.get("idempotencyKey"), third.get("idempotencyKey"))
        self.assertFalse(third.get("idempotentReplay"))
        db.close()
        Path(tmp.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
