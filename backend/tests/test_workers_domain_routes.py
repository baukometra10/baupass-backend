"""Workers domain blueprint — legacy /api/workers routes."""
from __future__ import annotations

import uuid
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
            "/api/workers/export.signatures.zip",
            "/api/workers/import-csv",
        ):
            self.assertIn(path, self.rules, msg=f"missing {path}")

    def test_v2_workers_requires_auth(self):
        res = self.client.get("/api/v2/workers")
        self.assertIn(res.status_code, (401, 403))

    def test_v2_workers_list_returns_array(self):
        login = self.client.post(
            "/api/login",
            json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
        )
        if login.status_code != 200:
            self.skipTest("demo login unavailable")
        token = login.get_json().get("token")
        company_name = f"WorkersRouteCo-{uuid.uuid4().hex[:8]}"
        company = self.client.post(
            "/api/companies",
            json={
                "name": company_name,
                "contact": "x",
                "adminPassword": "1234",
                "turnstilePassword": "1234",
                "turnstileCount": 0,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertIn(company.status_code, (200, 201), company.get_data(as_text=True))
        company_id = (company.get_json() or {}).get("company", {}).get("id") or (company.get_json() or {}).get("id")
        self.assertTrue(company_id)
        res = self.client.get(
            f"/api/v2/workers?company_id={company_id}",
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
