"""Workforce and operations domain blueprints."""
from __future__ import annotations

import unittest

from backend.server import app


class WorkforceOperationsRoutesTest(unittest.TestCase):
    def setUp(self):
        self.rules = [rule.rule for rule in app.url_map.iter_rules()]

    def test_workforce_routes(self):
        for path in (
            "/api/foreman/team-status",
            "/api/analytics/worker-trends",
            "/api/sync/conflicts",
        ):
            self.assertIn(path, self.rules, msg=path)

    def test_shift_via_shift_blueprint(self):
        self.assertIn("/api/shift/assignments", self.rules)

    def test_operations_routes(self):
        for path in (
            "/api/operations/snapshot",
            "/api/messages",
            "/api/incidents",
            "/api/media-evidence",
        ):
            self.assertIn(path, self.rules, msg=path)

    def test_no_duplicate_shift_assignments_get(self):
        keys = [
            (r.rule, m)
            for r in app.url_map.iter_rules()
            if r.rule == "/api/shift/assignments"
            for m in r.methods - {"HEAD", "OPTIONS"}
        ]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
