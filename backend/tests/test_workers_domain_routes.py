"""Workers domain blueprint — legacy /api/workers routes."""
from __future__ import annotations

import unittest

from backend.server import app


class WorkersDomainRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.rules = [rule.rule for rule in app.url_map.iter_rules()]

    def test_workers_list_requires_auth(self):
        res = self.client.get("/api/workers")
        self.assertIn(res.status_code, (401, 403))

    def test_core_worker_routes_registered(self):
        for path in (
            "/api/workers",
            "/api/workers/stats",
            "/api/workers/current-visitors",
            "/api/workers/export.csv",
            "/api/workers/import-csv",
        ):
            self.assertIn(path, self.rules, msg=f"missing {path}")

    def test_v2_workers_requires_auth(self):
        res = self.client.get("/api/v2/workers")
        self.assertIn(res.status_code, (401, 403))

    def test_v2_workers_list_returns_array(self):
        login = self.client.post(
            "/api/login",
            json={"username": "firma", "password": "1234", "loginScope": "company-admin"},
        )
        if login.status_code != 200:
            self.skipTest("demo login unavailable")
        token = login.get_json().get("token")
        res = self.client.get(
            "/api/v2/workers",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        body = res.get_json()
        self.assertIn("workers", body)
        self.assertIsInstance(body["workers"], list)

    def test_no_duplicate_worker_route_methods(self):
        keys = []
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/api/workers"):
                continue
            for method in rule.methods - {"HEAD", "OPTIONS"}:
                keys.append((rule.rule, method))
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
