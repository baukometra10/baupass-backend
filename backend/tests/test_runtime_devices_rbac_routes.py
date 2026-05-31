"""Runtime, devices, and RBAC domain blueprints."""
from __future__ import annotations

import unittest

from backend.server import app


class RuntimeDevicesRbacRoutesTest(unittest.TestCase):
    def setUp(self):
        self.rules = [rule.rule for rule in app.url_map.iter_rules()]

    def test_health_and_system(self):
        for path in ("/api/health", "/api/health/ready", "/api/system/status"):
            self.assertIn(path, self.rules, msg=path)

    def test_public_and_devices(self):
        for path in (
            "/api/public/branding",
            "/api/device/register",
            "/api/scan",
            "/api/worker-app/mobile-setup",
        ):
            self.assertIn(path, self.rules, msg=path)

    def test_rbac_and_admin_tools(self):
        for path in (
            "/api/roles",
            "/api/audit-trail",
            "/api/export",
            "/api/debug/imap-settings",
        ):
            self.assertIn(path, self.rules, msg=path)

    def test_health_live_no_auth(self):
        client = app.test_client()
        res = client.get("/api/health/live")
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
