"""Tests for API route probe helpers."""
from __future__ import annotations

import unittest

from backend.app.health.route_probe import build_api_route_probe
from backend.server import _route_methods_for, app


class HealthRouteProbeTests(unittest.TestCase):
    def test_build_api_route_probe_lists_missing_when_route_absent(self):
        probe = build_api_route_probe(lambda _path: set())
        self.assertFalse(probe["ok"])
        self.assertTrue(probe["missing"])

    def test_critical_routes_registered_in_test_app(self):
        probe = build_api_route_probe(_route_methods_for)
        missing = probe.get("missing") or []
        self.assertFalse(
            missing,
            msg=f"missing routes: {missing}",
        )


if __name__ == "__main__":
    unittest.main()
