"""Admin domain blueprint — /api/admin/* routes."""
from __future__ import annotations

import unittest

from backend.server import app


class AdminDomainRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.rules = [rule.rule for rule in app.url_map.iter_rules()]

    def test_admin_devices_requires_auth(self):
        res = self.client.get("/api/admin/devices")
        self.assertIn(res.status_code, (401, 403))

    def test_audit_logs_registered(self):
        self.assertIn("/api/audit-logs", self.rules)
        self.assertIn("/api/audit-events", self.rules)
        self.assertIn("/api/audit-events/summary", self.rules)
        self.assertIn("/api/audit-logs/export.csv", self.rules)

    def test_admin_routes_registered(self):
        for path in (
            "/api/admin/devices",
            "/api/admin/gate-devices",
            "/api/admin/database/backups",
            "/api/admin/device-events/dead-letters",
        ):
            self.assertIn(path, self.rules, msg=f"missing {path}")

    def test_v2_overview_requires_auth(self):
        res = self.client.get("/api/v2/admin/overview")
        self.assertIn(res.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
