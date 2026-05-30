"""Sector terminology and operating_sector normalization."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "platform" / "sector" / "catalog.py"
)


def _load_sector_catalog():
    spec = importlib.util.spec_from_file_location("sector_catalog_under_test", _CATALOG_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("sector catalog module not found")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_catalog = _load_sector_catalog()
normalize_operating_sector = _catalog.normalize_operating_sector
sector_config = _catalog.sector_config
all_sectors_public = _catalog.all_sectors_public


class SectorCatalogTests(unittest.TestCase):
    def test_normalize_aliases(self):
        self.assertEqual(normalize_operating_sector("manufacturing"), "manufacturing")
        self.assertEqual(normalize_operating_sector("industry"), "manufacturing")
        self.assertEqual(normalize_operating_sector("municipal"), "public_sector")
        self.assertEqual(normalize_operating_sector("unknown"), "construction")

    def test_sector_config_terms(self):
        cfg = sector_config("logistics", lang="ar")
        self.assertEqual(cfg["sector"], "logistics")
        self.assertIn("terms", cfg)
        self.assertTrue(cfg["terms"].get("navWorkers") or cfg["terms"].get("labelSite"))

    def test_all_sectors_public_count(self):
        sectors = all_sectors_public()
        self.assertGreaterEqual(len(sectors), 6)
        ids = {s["id"] for s in sectors}
        self.assertIn("government", ids)


if __name__ == "__main__":
    unittest.main()
