"""Companies domain blueprint."""
from __future__ import annotations

import unittest

from backend.server import app


class CompaniesDomainRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.rules = [rule.rule for rule in app.url_map.iter_rules()]

    def test_companies_list_requires_auth(self):
        res = self.client.get("/api/companies")
        self.assertIn(res.status_code, (401, 403))

    def test_subcompanies_registered(self):
        self.assertIn("/api/subcompanies", self.rules)

    def test_company_routes_registered(self):
        for path in (
            "/api/companies",
            "/api/companies/document-emails/export",
            "/api/companies/<company_id>/mail-settings",
            "/api/companies/<company_id>/plan-features",
        ):
            self.assertIn(path, self.rules, msg=f"missing {path}")


if __name__ == "__main__":
    unittest.main()
