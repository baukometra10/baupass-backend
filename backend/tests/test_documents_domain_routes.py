"""Documents domain blueprint."""
from __future__ import annotations

import unittest

from backend.server import app


class DocumentsDomainRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.rules = [rule.rule for rule in app.url_map.iter_rules()]

    def test_inbox_requires_auth(self):
        res = self.client.get("/api/documents/inbox")
        self.assertIn(res.status_code, (401, 403))

    def test_routes_registered(self):
        for path in ("/api/documents/inbox", "/api/documents/expiring", "/api/documents/imap/trigger"):
            self.assertIn(path, self.rules)


if __name__ == "__main__":
    unittest.main()
