"""Notifications domain blueprint."""
from __future__ import annotations

import unittest

from backend.server import app


class NotificationsDomainRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.rules = [rule.rule for rule in app.url_map.iter_rules()]

    def test_system_alerts_requires_auth(self):
        res = self.client.get("/api/system-alerts")
        self.assertIn(res.status_code, (401, 403))

    def test_notification_routes_registered(self):
        for path in (
            "/api/notifications",
            "/api/system-alerts",
            "/api/push/trigger-checkout-reminders",
        ):
            self.assertIn(path, self.rules, msg=f"missing {path}")

    def test_v2_inbox_requires_auth(self):
        res = self.client.get("/api/v2/notifications/inbox")
        self.assertIn(res.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
