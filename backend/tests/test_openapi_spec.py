"""Tests for OpenAPI baseline spec."""
from __future__ import annotations

import unittest

from backend.app.api.openapi_spec import build_openapi_document


class OpenApiSpecTests(unittest.TestCase):
    def test_builds_valid_baseline(self):
        doc = build_openapi_document("https://staging.example.com")
        self.assertEqual(doc["openapi"], "3.0.3")
        self.assertIn("/api/login", doc["paths"])
        self.assertIn("/api/integrations/cameras/bulk", doc["paths"])
        self.assertIn("bearerAuth", doc["components"]["securitySchemes"])
        self.assertEqual(doc["servers"][0]["url"], "https://staging.example.com")

    def test_self_reference_path(self):
        doc = build_openapi_document()
        self.assertIn("/api/v1/openapi.json", doc["paths"])


if __name__ == "__main__":
    unittest.main()
