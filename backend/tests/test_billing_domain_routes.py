"""Billing domain blueprint — core invoice GET routes."""
from __future__ import annotations

import unittest

from backend.server import app


class BillingDomainRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.rules = {rule.rule: rule.endpoint for rule in app.url_map.iter_rules()}

    def test_invoices_list_requires_auth(self):
        res = self.client.get("/api/invoices")
        self.assertIn(res.status_code, (401, 403))

    def test_invoices_routes_registered_on_blueprint(self):
        for path in (
            "/api/invoices",
            "/api/invoices/send",
            "/api/invoices/export.csv",
            "/api/invoices/ops-metrics",
            "/api/invoices/monthly-cycle-status",
            "/api/invoices/dead-letters",
            "/api/invoices/next-number",
            "/api/invoices/approvals/pending",
            "/api/invoices/trigger-dunning",
        ):
            self.assertIn(path, self.rules, msg=f"missing {path}")

    def test_no_duplicate_invoices_routes_on_app(self):
        invoice_rules = [r for r in self.rules if r.startswith("/api/invoices")]
        self.assertEqual(len(invoice_rules), len(set(invoice_rules)))

    def test_v2_billing_overview_requires_auth(self):
        res = self.client.get("/api/v2/billing/overview")
        self.assertIn(res.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
