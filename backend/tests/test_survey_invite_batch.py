"""Survey invite batch behaviour."""
from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch

from backend.app.domains.admin.survey_dispatch import send_survey_invites_batch


class SurveyInviteBatchTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE settings (
                id INTEGER PRIMARY KEY,
                smtp_host TEXT,
                smtp_sender_email TEXT,
                smtp_sender_name TEXT
            );
            INSERT INTO settings (id, smtp_host, smtp_sender_email) VALUES (1, 'smtp.test', 'noreply@test.local');
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                username TEXT,
                name TEXT,
                role TEXT,
                company_id TEXT,
                email TEXT
            );
            INSERT INTO users VALUES ('u1', 'admin1', 'Admin One', 'company-admin', 'cmp-a', 'admin1@test.local');
            CREATE TABLE audit_logs (
                id TEXT PRIMARY KEY,
                event_type TEXT,
                actor_user_id TEXT,
                company_id TEXT,
                created_at TEXT
            );
            CREATE TABLE feature_usage_events (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                company_id TEXT,
                created_at TEXT
            );
            CREATE TABLE system_satisfaction_surveys (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                created_at TEXT
            );
            """
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    @patch("backend.app.domains.admin.survey_dispatch.check_mail_provider_ready")
    @patch("backend.app.domains.admin.survey_dispatch.send_survey_invite_email")
    def test_send_all_skips_usage_gate(self, send_one, mail_ready):
        mail_ready.return_value = {"configured": True, "providers": ["smtp"]}
        send_one.return_value = {"ok": True, "email": "admin1@test.local"}

        result = send_survey_invites_batch(self.db, company_id="cmp-a", send_all=True)

        self.assertEqual(result.get("sent"), 1)
        send_one.assert_called_once()
        self.assertTrue(send_one.call_args.kwargs.get("skip_usage_check"))

    @patch("backend.app.domains.admin.survey_dispatch.check_mail_provider_ready")
    def test_no_recipients_when_no_email_users(self, mail_ready):
        mail_ready.return_value = {"configured": True, "providers": ["smtp"]}
        self.db.execute("UPDATE users SET email = ''")
        self.db.commit()

        result = send_survey_invites_batch(self.db, company_id="cmp-a", send_all=True)

        self.assertEqual(result.get("error"), "no_recipients")


if __name__ == "__main__":
    unittest.main()
