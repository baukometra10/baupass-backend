"""Work time normalization (HH:MM vs browser HH:MM:SS)."""
from __future__ import annotations

import re
import unittest


def normalize_work_time_value(value):
    """Mirror of backend.server.normalize_work_time_value for unit tests."""
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if len(normalized) >= 8 and normalized[2] == ":" and normalized[5] == ":":
        normalized = normalized[:5]
    elif len(normalized) > 5:
        normalized = normalized[:5]
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", normalized):
        raise ValueError("invalid_work_time")
    return normalized


class WorkTimeNormalizeTests(unittest.TestCase):
    def test_accepts_hh_mm_ss(self):
        self.assertEqual(normalize_work_time_value("08:00:00"), "08:00")
        self.assertEqual(normalize_work_time_value("18:00:00"), "18:00")

    def test_accepts_hh_mm(self):
        self.assertEqual(normalize_work_time_value("07:30"), "07:30")

    def test_empty_allowed(self):
        self.assertEqual(normalize_work_time_value(""), "")
        self.assertEqual(normalize_work_time_value(None), "")


if __name__ == "__main__":
    unittest.main()
