"""Tests for AI branding guard (legacy name sanitization)."""
from __future__ import annotations

import unittest

from backend.app.platform.ai.brand_guard import sanitize_ai_answer, sanitize_legacy_brand


class BrandGuardTests(unittest.TestCase):
    def test_replaces_control_pass(self):
        self.assertIn("WorkPass", sanitize_legacy_brand("Control Pass was the old name."))
        self.assertNotIn("Control Pass", sanitize_legacy_brand("Control Pass was the old name."))

    def test_replaces_baupass_control(self):
        out = sanitize_legacy_brand("BauPass Control is outdated.")
        self.assertIn("WorkPass", out)
        self.assertNotIn("Control", out.split("WorkPass")[0])

    def test_sanitize_ai_answer_none(self):
        self.assertIsNone(sanitize_ai_answer(None))


if __name__ == "__main__":
    unittest.main()
