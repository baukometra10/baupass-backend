"""Auth domain blueprint — login, 2FA, session routes under /api."""
from __future__ import annotations

import unittest

from backend.server import app


class AuthDomainRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.rules = {rule.rule: rule.endpoint for rule in app.url_map.iter_rules()}

    def test_session_bootstrap_unauthenticated(self):
        res = self.client.get("/api/session/bootstrap")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data.get("authenticated"))

    def test_logout_requires_auth(self):
        res = self.client.post("/api/logout")
        self.assertIn(res.status_code, (401, 403))

    def test_login_route_registered(self):
        self.assertIn("/api/login", self.rules)

    def test_me_heartbeat_and_email_registered(self):
        self.assertIn("/api/me/heartbeat", self.rules)
        self.assertIn("/api/me/email", self.rules)

    def test_twofa_routes_registered(self):
        self.assertIn("/api/me/2fa", self.rules)
        self.assertIn("/api/me/2fa/activate", self.rules)
        self.assertIn("/api/me/2fa/disable", self.rules)

    def test_password_reset_routes_registered(self):
        self.assertIn("/api/auth/request-password-reset", self.rules)

    def test_login_invalid_credentials(self):
        res = self.client.post(
            "/api/login",
            json={"username": "nonexistent-user-xyz", "password": "wrong"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("error"), "invalid_credentials")


if __name__ == "__main__":
    unittest.main()
