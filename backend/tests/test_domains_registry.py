"""Domain registry — all blueprints load; no duplicate API route methods."""
from __future__ import annotations

import unittest

from backend.app.domains.registry import DOMAIN_REGISTRARS
from backend.server import app


class DomainsRegistryTest(unittest.TestCase):
    def test_registry_has_expected_domains(self):
        names = [e.name for e in DOMAIN_REGISTRARS]
        for required in (
            "auth",
            "runtime",
            "http",
            "workers",
            "billing",
            "access",
        ):
            self.assertIn(required, names)

    def test_http_registered_last(self):
        self.assertEqual(DOMAIN_REGISTRARS[-1].name, "http")

    def test_no_duplicate_api_route_methods(self):
        keys: list[tuple[str, str]] = []
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/api/"):
                continue
            for method in rule.methods - {"HEAD", "OPTIONS"}:
                keys.append((rule.rule, method))
        self.assertEqual(len(keys), len(set(keys)), msg="duplicate API route+method")

    def test_zero_app_route_decorators_in_server_module(self):
        import backend.server as srv

        source = open(srv.__file__, encoding="utf-8").read()
        self.assertNotIn('@app.get("/api/', source)
        self.assertNotIn('@app.post("/api/', source)

    def test_qr_and_health_routes(self):
        rules = {r.rule for r in app.url_map.iter_rules()}
        self.assertIn("/api/qr.png", rules)
        self.assertIn("/api/health/live", rules)
        self.assertIn("/", rules)


if __name__ == "__main__":
    unittest.main()
