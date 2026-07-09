"""Survey email resolution and invite candidates (billing fallback)."""
from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backend.app.domains.admin.survey_dispatch import (
    _resolve_survey_email,
    list_invite_candidates,
    send_survey_invite_email,
)
from backend.app.domains.admin.usage_analytics import survey_pending_for_user


class SurveyEmailResolutionTest(unittest.TestCase):
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
            CREATE TABLE companies (
                id TEXT PRIMARY KEY,
                name TEXT,
                billing_email TEXT,
                document_email TEXT,
                survey_prompt_enabled INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT
            );
            INSERT INTO companies VALUES ('cmp-a', 'Co A', 'billing@firma.local', '', 1, NULL);
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                username TEXT,
                name TEXT,
                role TEXT,
                company_id TEXT,
                email TEXT
            );
            INSERT INTO users VALUES ('u1', 'admin1', 'Admin One', 'company-admin', 'cmp-a', '');
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

    def test_resolve_survey_email_uses_billing_when_user_email_empty(self):
        email, source = _resolve_survey_email(
            self.db,
            {"id": "u1", "email": "", "company_id": "cmp-a"},
        )
        self.assertEqual(email, "billing@firma.local")
        self.assertEqual(source, "billing")

    def test_resolve_survey_email_prefers_user_email(self):
        email, source = _resolve_survey_email(
            self.db,
            {"id": "u1", "email": "admin@firma.local", "company_id": "cmp-a"},
        )
        self.assertEqual(email, "admin@firma.local")
        self.assertEqual(source, "user")

    def test_list_invite_candidates_includes_billing_email(self):
        data = list_invite_candidates(self.db, company_id="cmp-a")
        candidates = data.get("candidates") or []
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["email"], "billing@firma.local")
        self.assertEqual(candidates[0]["emailSource"], "billing")
        self.assertTrue(candidates[0]["eligible"])
        self.assertTrue(candidates[0]["surveyPromptEnabled"])

    @patch("backend.app.domains.admin.survey_dispatch.check_mail_provider_ready")
    @patch("backend.app.domains.admin.survey_dispatch.send_survey_invite_email")
    def test_send_batch_uses_resolved_billing_email(self, send_one, mail_ready):
        from backend.app.domains.admin.survey_dispatch import send_survey_invites_batch

        mail_ready.return_value = {"configured": True, "providers": ["smtp"]}
        send_one.return_value = {"ok": True, "email": "billing@firma.local", "emailSource": "billing"}

        result = send_survey_invites_batch(self.db, company_id="cmp-a", send_all=True)

        self.assertEqual(result.get("sent"), 1)
        send_one.assert_called_once()
        user_arg = send_one.call_args.args[1]
        self.assertEqual(user_arg.get("email"), "")

    def test_survey_pending_when_prompt_enabled_skips_usage_gate(self):
        pending = survey_pending_for_user(
            self.db,
            {"id": "u1", "company_id": "cmp-a", "role": "company-admin"},
        )
        self.assertTrue(pending.get("pending"))
        self.assertTrue(pending.get("surveyPromptEnabled"))

    def test_survey_pending_false_without_email_path_when_submitted_recently(self):
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.db.execute(
            "INSERT INTO system_satisfaction_surveys (id, user_id, created_at) VALUES (?, ?, ?)",
            ("s1", "u1", now),
        )
        self.db.commit()
        pending = survey_pending_for_user(
            self.db,
            {"id": "u1", "company_id": "cmp-a", "role": "company-admin"},
        )
        self.assertFalse(pending.get("pending"))
        self.assertEqual(pending.get("reason"), "recent_submission")

    @patch("backend.app.domains.admin.survey_dispatch.check_mail_provider_ready")
    @patch("backend.server._send_email_api_then_smtp")
    def test_send_survey_invite_email_to_billing(self, send_mail, mail_ready):
        mail_ready.return_value = {"configured": True, "providers": ["smtp"]}
        send_mail.return_value = (True, None, "smtp")
        with patch("backend.server.log_audit", return_value=None):
            result = send_survey_invite_email(
                self.db,
                {"id": "u1", "username": "admin1", "name": "Admin", "role": "company-admin", "company_id": "cmp-a", "email": ""},
                skip_usage_check=True,
            )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("email"), "billing@firma.local")
        self.assertEqual(result.get("emailSource"), "billing")


if __name__ == "__main__":
    unittest.main()
