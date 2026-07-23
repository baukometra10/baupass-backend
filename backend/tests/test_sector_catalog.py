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
sector_noun = _catalog.sector_noun


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

    def test_sector_config_admin_v2_terms(self):
        cfg = sector_config("public_sector", lang="de")
        terms = cfg["terms"]
        self.assertIn("overviewOnSite", terms)
        self.assertNotIn("Baustelle", terms.get("overviewOnSite", ""))
        self.assertIn("Standort", terms["overviewOnSite"])
        self.assertIn("tabWorkers", terms)
        self.assertEqual(terms["tabWorkers"], "Mitarbeitende")
        self.assertIn("sectorBanner", terms)

    def test_sector_terms_differ_by_vertical(self):
        bau = sector_config("construction", lang="de")["terms"]
        air = sector_config("aviation", lang="de")["terms"]
        self.assertNotEqual(bau.get("termSite"), air.get("termSite"))
        self.assertIn("Baustelle", bau.get("termSite", ""))
        self.assertIn("Terminal", air.get("termSite", ""))
        self.assertEqual(air.get("tabWorkers"), "Berechtigte")

    def test_sector_noun_helper(self):
        air = sector_config("aviation", lang="de")["terms"]
        self.assertEqual(sector_noun(air, "termSite", "Standort"), "Terminal")
        self.assertEqual(sector_noun({}, "termSite", "Standort"), "Standort")

    def test_guidance_uses_sector_terms(self):
        from backend.app.platform.reports.guidance import build_operational_guidance

        items = build_operational_guidance(
            {"workersOnSite": 0, "kpis": {}},
            terms={"termWorkers": "Berechtigte", "termSite": "Terminal"},
        )
        titles = " ".join(str(i.get("titleDe") or "") for i in items)
        self.assertIn("Berechtigte", titles)
        self.assertIn("Terminal", titles)
        self.assertNotIn("Baustelle", titles)

    def test_live_context_uses_sector_vocabulary(self):
        from backend.app.platform.ai.context_builder import format_live_context_block

        block = format_live_context_block(
            {
                "companyName": "Demo Air",
                "workersOnSite": 2,
                "operatingSector": "aviation",
                "sectorLabel": "Luftfahrt",
                "sectorTerms": {
                    "termWorkers": "Berechtigte",
                    "termSite": "Terminal",
                    "termGate": "Kontrollpunkt",
                },
            },
            lang="de",
        )
        self.assertIn("Terminal", block)
        self.assertIn("Berechtigte", block)
        self.assertIn("Kontrollpunkt", block)
        self.assertNotIn("Baustelle", block)

    def test_experience_sectorizes_prompts(self):
        from backend.app.platform.ai.experience import enrich_insights_dashboard

        dash = {
            "cards": [{"id": "onsite", "value": 0}],
            "recommendations": ["investigate_low_activity_sites"],
            "snapshot": {},
        }
        enrich_insights_dashboard(
            dash,
            company_id="c1",
            lang="de",
            terms={"termWorkers": "Berechtigte", "termSite": "Terminal"},
        )
        prompt = (dash["cards"][0].get("actions") or [{}])[-1].get("prompt") or ""
        self.assertIn("Terminal", prompt)
        self.assertNotIn("Baustelle", prompt)
        labels = " ".join(a.get("label") or "" for a in dash.get("nextActions") or [])
        self.assertIn("Terminal", labels)

    def test_worker_sector_terms(self):
        cfg = sector_config("manufacturing", lang="de")
        terms = cfg["terms"]
        self.assertEqual(terms.get("fieldSite"), "Werk / Halle")
        self.assertIn("Werk", terms.get("proximityNotScheduledToday", ""))
        self.assertNotIn("Baustelle", terms.get("proximityNotScheduledToday", ""))
        self.assertEqual(terms.get("nextStepConstructionTitle"), "Werk zuerst")

        aviation = sector_config("aviation", lang="de")["terms"]
        self.assertIn("Terminal", aviation.get("fieldSite", ""))

        sectors = all_sectors_public()
        self.assertGreaterEqual(len(sectors), 7)
        ids = {s["id"] for s in sectors}
        self.assertIn("government", ids)


if __name__ == "__main__":
    unittest.main()
