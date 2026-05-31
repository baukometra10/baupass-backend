"""Access domain blueprint — core routes registered under /api."""
from __future__ import annotations

import unittest

from backend.server import app


class AccessDomainRoutesTest(unittest.TestCase):
    def setUp(self):
        self.rules = {rule.rule: rule.endpoint for rule in app.url_map.iter_rules()}

    def test_access_logs_route(self):
        self.assertIn("/api/access-logs", self.rules)

    def test_access_logs_latest_route(self):
        self.assertIn("/api/access-logs/latest", self.rules)

    def test_gates_tap_route(self):
        self.assertIn("/api/gates/tap", self.rules)

    def test_gates_tap_requires_key(self):
        client = app.test_client()
        res = client.post("/api/gates/tap", json={})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json().get("error"), "gate_unauthorized")

    def test_access_logs_summary_route(self):
        self.assertIn("/api/access-logs/summary", self.rules)

    def test_gates_heartbeat_route(self):
        self.assertIn("/api/gates/heartbeat", self.rules)


if __name__ == "__main__":
    unittest.main()
