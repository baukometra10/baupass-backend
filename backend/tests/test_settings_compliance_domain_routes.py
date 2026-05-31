"""Settings and compliance domain blueprints."""
from __future__ import annotations

import unittest

from backend.server import app


class SettingsComplianceRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.rules = [rule.rule for rule in app.url_map.iter_rules()]

    def test_settings_requires_auth(self):
        res = self.client.get("/api/settings")
        self.assertIn(res.status_code, (401, 403))

    def test_compliance_overview_requires_auth(self):
        res = self.client.get("/api/compliance/overview")
        self.assertIn(res.status_code, (401, 403))

    def test_routes_registered(self):
        for path in (
            "/api/settings",
            "/api/settings/imap/test",
            "/api/compliance/overview",
            "/api/compliance/expiring-docs",
            "/api/compliance-reports",
        ):
            self.assertIn(path, self.rules, msg=path)


if __name__ == "__main__":
    unittest.main()
