"""Usage analytics and satisfaction survey API tests."""
from __future__ import annotations

import unittest

from backend.server import app


class UsageAnalyticsRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.rules = [rule.rule for rule in app.url_map.iter_rules()]

    def test_usage_stats_route_registered(self):
        self.assertIn("/api/v2/admin/usage-stats", self.rules)

    def test_usage_trends_route_registered(self):
        self.assertIn("/api/v2/admin/usage-trends", self.rules)

    def test_worker_usage_route_registered(self):
        self.assertIn("/api/worker-app/usage/event", self.rules)

    def test_satisfaction_routes_registered(self):
        for path in (
            "/api/v2/admin/satisfaction-surveys",
            "/api/v2/admin/satisfaction-survey/mail-status",
            "/api/v2/admin/satisfaction-survey/invite-candidates",
            "/api/v2/admin/satisfaction-survey/invite",
            "/api/v2/admin/feature-usage",
            "/api/v2/satisfaction-survey",
            "/api/v2/satisfaction-survey/pending",
            "/api/v2/usage/event",
        ):
            self.assertIn(path, self.rules, msg=f"missing {path}")

    def test_usage_stats_requires_auth(self):
        res = self.client.get("/api/v2/admin/usage-stats")
        self.assertIn(res.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
