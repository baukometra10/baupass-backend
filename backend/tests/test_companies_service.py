"""CompaniesService — repository-backed list/create."""
from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch

from backend.app.domains.companies.service import CompaniesService


class CompaniesServiceTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE companies (
                id TEXT PRIMARY KEY,
                name TEXT,
                plan TEXT,
                deleted_at TEXT,
                status TEXT,
                work_start_time TEXT,
                work_end_time TEXT,
                access_mode TEXT,
                site_geofence_radius_meters INTEGER,
                site_auto_checkin INTEGER,
                site_auto_logout_on_leave INTEGER
            );
            CREATE TABLE subcompanies (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                name TEXT,
                contact TEXT,
                status TEXT,
                deleted_at TEXT
            );
            CREATE TABLE workers (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                deleted_at TEXT,
                status TEXT
            );
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                password_hash TEXT,
                name TEXT,
                role TEXT,
                company_id TEXT,
                api_key_hash TEXT,
                is_active INTEGER DEFAULT 1,
                email TEXT,
                twofa_enabled INTEGER DEFAULT 0
            );
            CREATE TABLE otp_codes (
                user_id TEXT,
                code TEXT
            );
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                last_seen TEXT
            );
            INSERT INTO companies VALUES (
                'cmp-a', 'Alpha', 'enterprise', NULL, 'aktiv',
                '', '', 'gate', 100, 1, 1
            );
            INSERT INTO companies VALUES (
                'cmp-b', 'Beta', 'starter', '2020-01-01', 'pausiert',
                '', '', 'gate', 100, 1, 1
            );
            INSERT INTO users (
                id, username, password_hash, name, role, company_id, email, twofa_enabled
            ) VALUES (
                'usr-admin', 'alphaadmin', 'hash', 'Alpha Admin', 'company-admin', 'cmp-a', '', 0
            );
            """
        )
        self.conn.commit()
        self.svc = CompaniesService()

    def test_get_admin_security(self):
        result = self.svc.get_admin_security(self.conn, "cmp-a")
        self.assertEqual(result["body"]["username"], "alphaadmin")
        self.assertFalse(result["body"]["twofa_enabled"])

    def test_set_admin_security_enables_2fa(self):
        result = self.svc.set_admin_security(
            self.conn, "cmp-a", email="admin@test.de", enable_2fa=True
        )
        self.assertTrue(result["body"]["twofa_enabled"])
        row = self.conn.execute(
            "SELECT email, twofa_enabled FROM users WHERE id = ?", ("usr-admin",)
        ).fetchone()
        self.assertEqual(row["email"], "admin@test.de")
        self.assertEqual(int(row["twofa_enabled"]), 1)

    def test_set_admin_password_rejects_short(self):
        result = self.svc.set_admin_password(self.conn, "cmp-a", new_password="short")
        self.assertEqual(result["status"], 400)

    def test_set_admin_password_ok(self):
        result = self.svc.set_admin_password(
            self.conn, "cmp-a", new_password="longenough"
        )
        self.assertTrue(result["body"]["ok"])

    def test_list_companies_hides_deleted_by_default(self):
        user = {"role": "superadmin", "company_id": None}
        items = self.svc.list_companies(self.conn, user, include_deleted=False)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "cmp-a")

    def test_list_companies_include_deleted(self):
        user = {"role": "superadmin", "company_id": None}
        items = self.svc.list_companies(self.conn, user, include_deleted=True)
        self.assertEqual(len(items), 2)

    def test_list_companies_company_admin_scope(self):
        user = {"role": "company-admin", "company_id": "cmp-a"}
        items = self.svc.list_companies(self.conn, user, include_deleted=False)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Alpha")

    def test_create_subcompany(self):
        user = {"role": "superadmin", "company_id": None}
        # patch plan check — enterprise has subcompanies in PLAN_FEATURES
        result = self.svc.create_subcompany(
            self.conn,
            user,
            company_id="cmp-a",
            name="Sub One",
            contact="c@test.de",
        )
        self.assertIn("item", result)
        self.assertEqual(result["status"], 201)
        self.assertIn("audit", result)
        row = self.conn.execute(
            "SELECT name FROM subcompanies WHERE company_id = ?", ("cmp-a",)
        ).fetchone()
        self.assertEqual(row["name"], "Sub One")


    def test_create_company_rejects_short_password(self):
        result = self.svc.create_company(
            self.conn,
            {"name": "Gamma", "adminPassword": "ab", "turnstileCount": 1},
        )
        self.assertEqual(result.get("status"), 400)
        self.assertEqual(result["error"]["error"], "password_too_short")

    @patch("backend.server.rematch_inbox_company_links")
    def test_update_company_changes_name(self, _rematch):
        self.conn.executescript(
            """
            DROP TABLE companies;
            CREATE TABLE companies (
                id TEXT PRIMARY KEY,
                name TEXT,
                plan TEXT,
                deleted_at TEXT,
                customer_number TEXT,
                contact TEXT,
                billing_email TEXT,
                billing_street TEXT,
                billing_zip_city TEXT,
                document_email TEXT,
                access_host TEXT,
                branding_preset TEXT,
                status TEXT,
                trial_ends_at TEXT,
                invoice_email_lang TEXT,
                portal_display_name TEXT,
                branding_accent_color TEXT,
                branding_logo_data TEXT,
                report_timezone TEXT,
                operating_sector TEXT
            );
            INSERT INTO companies (
                id, name, plan, deleted_at, customer_number, contact, billing_email,
                billing_street, billing_zip_city, document_email, access_host,
                branding_preset, status, trial_ends_at, invoice_email_lang,
                portal_display_name, branding_accent_color, branding_logo_data,
                report_timezone, operating_sector
            ) VALUES (
                'cmp-a', 'Alpha', 'enterprise', NULL, 'K001', '', '', '', '', '', '',
                '', 'aktiv', '', 'de', '', '', '', '', 'construction'
            );
            """
        )
        self.conn.commit()
        result = self.svc.update_company(self.conn, "cmp-a", {"name": "Alpha Renamed"})
        self.assertEqual(result["body"], {"ok": True})
        row = self.conn.execute("SELECT name FROM companies WHERE id = ?", ("cmp-a",)).fetchone()
        self.assertEqual(row["name"], "Alpha Renamed")

    @patch("backend.server.rematch_inbox_company_links")
    def test_update_company_rejects_oversized_logo(self, _rematch):
        self.conn.executescript(
            """
            DROP TABLE companies;
            CREATE TABLE companies (
                id TEXT PRIMARY KEY,
                name TEXT,
                plan TEXT,
                deleted_at TEXT,
                customer_number TEXT,
                contact TEXT,
                billing_email TEXT,
                billing_street TEXT,
                billing_zip_city TEXT,
                document_email TEXT,
                access_host TEXT,
                branding_preset TEXT,
                status TEXT,
                trial_ends_at TEXT,
                invoice_email_lang TEXT,
                portal_display_name TEXT,
                branding_accent_color TEXT,
                branding_logo_data TEXT,
                report_timezone TEXT,
                operating_sector TEXT
            );
            INSERT INTO companies (
                id, name, plan, deleted_at, customer_number, contact, billing_email,
                billing_street, billing_zip_city, document_email, access_host,
                branding_preset, status, trial_ends_at, invoice_email_lang,
                portal_display_name, branding_accent_color, branding_logo_data,
                report_timezone, operating_sector
            ) VALUES (
                'cmp-a', 'Alpha', 'enterprise', NULL, 'K001', '', '', '', '', '', '',
                '', 'aktiv', '', 'de', '', '', '', '', 'construction'
            );
            """
        )
        self.conn.commit()
        huge = "data:image/png;base64," + ("A" * 200_000)
        result = self.svc.update_company(self.conn, "cmp-a", {"brandingLogoData": huge})
        self.assertEqual(result["status"], 400)
        self.assertEqual(result["error"]["error"], "logo_too_large")

    def test_update_company_not_found(self):
        result = self.svc.update_company(self.conn, "missing", {"name": "X"})
        self.assertEqual(result["status"], 404)

    def test_mail_access_forbidden(self):
        user = {"role": "company-admin", "company_id": "cmp-other"}
        denied = self.svc.check_mail_access(user, {"id": "cmp-a", "deleted_at": None})
        self.assertEqual(denied["status"], 403)

    def test_create_mail_settings_duplicate(self):
        self.conn.executescript(
            """
            CREATE TABLE company_mail_settings (
                company_id TEXT PRIMARY KEY,
                mail_provider TEXT,
                imap_host TEXT, imap_port INTEGER, imap_username TEXT,
                imap_password TEXT, imap_use_tls INTEGER,
                smtp_host TEXT, smtp_port INTEGER, smtp_username TEXT,
                smtp_password TEXT, smtp_use_tls INTEGER,
                brevo_api_key TEXT, sender_email TEXT, sender_name TEXT,
                last_test_inbound TEXT, last_test_outbound TEXT,
                test_inbound_status TEXT, test_outbound_status TEXT,
                created_at TEXT, updated_at TEXT
            );
            INSERT INTO company_mail_settings (
                company_id, mail_provider,
                imap_host, imap_port, imap_username, imap_password, imap_use_tls,
                smtp_host, smtp_port, smtp_username, smtp_password, smtp_use_tls,
                brevo_api_key, sender_email, sender_name,
                last_test_inbound, last_test_outbound, test_inbound_status, test_outbound_status,
                created_at, updated_at
            ) VALUES (
                'cmp-a', 'gmail',
                '', 993, '', '', 1,
                '', 587, '', '', 1,
                '', '', '',
                '', '', 'pending', 'pending',
                '2020-01-01', '2020-01-01'
            );
            """
        )
        self.conn.commit()
        user = {"role": "superadmin", "company_id": None}
        result = self.svc.create_mail_settings(self.conn, user, "cmp-a", {"mailProvider": "gmail"})
        self.assertEqual(result["status"], 409)

    def test_delete_company_protects_default(self):
        result = self.svc.delete_company(self.conn, "cmp-default", force=False)
        self.assertEqual(result["status"], 400)

    def test_delete_company_blocks_when_workers_present(self):
        self.conn.execute(
            "INSERT INTO workers VALUES ('w1', 'cmp-a', NULL, 'aktiv')"
        )
        self.conn.commit()
        result = self.svc.delete_company(self.conn, "cmp-a", force=False)
        self.assertEqual(result["status"], 400)
        self.assertEqual(result["error"]["error"], "company_has_workers")

    def test_delete_company_soft_delete(self):
        result = self.svc.delete_company(self.conn, "cmp-a", force=False)
        self.assertEqual(result["body"], {"ok": True, "force": False})
        row = self.conn.execute(
            "SELECT deleted_at, status FROM companies WHERE id = ?", ("cmp-a",)
        ).fetchone()
        self.assertIsNotNone(row["deleted_at"])
        self.assertEqual(row["status"], "pausiert")

    def test_work_times_forbidden(self):
        user = {"role": "company-admin", "company_id": "cmp-other"}
        result = self.svc.get_work_times(self.conn, user, "cmp-a")
        self.assertEqual(result["status"], 403)

    def test_update_work_times_invalid_time(self):
        user = {"role": "superadmin", "company_id": None}
        result = self.svc.update_work_times(
            self.conn, user, "cmp-a", {"workStartTime": "99:99"}
        )
        self.assertEqual(result["status"], 400)

    def test_update_work_times_persists(self):
        user = {"role": "superadmin", "company_id": None}
        result = self.svc.update_work_times(
            self.conn,
            user,
            "cmp-a",
            {
                "workStartTime": "07:00",
                "workEndTime": "16:00",
                "accessMode": "gate",
            },
        )
        self.assertTrue(result["body"]["ok"])
        row = self.conn.execute(
            "SELECT work_start_time, work_end_time FROM companies WHERE id = ?",
            ("cmp-a",),
        ).fetchone()
        self.assertEqual(row["work_start_time"], "07:00")
        self.assertEqual(row["work_end_time"], "16:00")

    def test_list_turnstiles_forbidden(self):
        user = {"role": "company-admin", "company_id": "cmp-other"}
        result = self.svc.list_turnstiles(self.conn, user, "cmp-a")
        self.assertEqual(result["status"], 403)

    def test_add_turnstile(self):
        result = self.svc.add_turnstile(self.conn, "cmp-a", password="secret1")
        self.assertEqual(result["status"], 201)
        self.assertTrue(result["body"]["ok"])
        count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE company_id = ? AND role = 'turnstile'",
            ("cmp-a",),
        ).fetchone()["c"]
        self.assertEqual(count, 1)

    def test_reset_turnstile_password(self):
        self.svc.add_turnstile(self.conn, "cmp-a", password="secret1")
        row = self.conn.execute(
            "SELECT id FROM users WHERE company_id = ? AND role = 'turnstile'",
            ("cmp-a",),
        ).fetchone()
        user = {"role": "superadmin", "company_id": None}
        result = self.svc.reset_turnstile_password(
            self.conn, user, "cmp-a", row["id"], password="newpass"
        )
        self.assertEqual(result["body"], {"ok": True})

    def test_toggle_turnstile_active(self):
        self.svc.add_turnstile(self.conn, "cmp-a", password="secret1")
        row = self.conn.execute(
            "SELECT id FROM users WHERE company_id = ? AND role = 'turnstile'",
            ("cmp-a",),
        ).fetchone()
        result = self.svc.toggle_turnstile_active(self.conn, "cmp-a", row["id"])
        self.assertFalse(result["body"]["isActive"])

    def test_restore_company(self):
        self.conn.execute(
            "UPDATE companies SET deleted_at = '2020-01-01', status = 'pausiert' WHERE id = ?",
            ("cmp-a",),
        )
        self.conn.commit()
        result = self.svc.restore_company(self.conn, "cmp-a")
        self.assertTrue(result["body"]["ok"])
        row = self.conn.execute(
            "SELECT deleted_at, status FROM companies WHERE id = ?", ("cmp-a",)
        ).fetchone()
        self.assertIsNone(row["deleted_at"])
        self.assertEqual(row["status"], "aktiv")

    def test_get_plan_features(self):
        user = {"role": "company-admin", "company_id": "cmp-a"}
        result = self.svc.get_plan_features(self.conn, user, "cmp-a")
        self.assertEqual(result["body"]["plan"], "enterprise")
        self.assertIn("features", result["body"])

    def test_toggle_review_access(self):
        self.conn.execute(
            "ALTER TABLE companies ADD COLUMN review_enabled INTEGER DEFAULT 0"
        )
        self.conn.execute(
            "ALTER TABLE companies ADD COLUMN review_token TEXT DEFAULT ''"
        )
        self.conn.commit()
        result = self.svc.toggle_review_access(self.conn, "cmp-a")
        self.assertEqual(result["body"]["review_enabled"], 1)
        self.assertTrue(result["body"]["review_token"])


if __name__ == "__main__":
    unittest.main()
