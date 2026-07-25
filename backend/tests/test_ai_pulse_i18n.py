"""Pulse recommendation packs cover all 8 UI languages."""
from __future__ import annotations

from backend.app.platform.ai import operator_pulse as pulse_mod


class _FakeDb:
    def execute(self, sql, params=None):
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def commit(self):
        return None


def test_pulse_labels_for_tr_fr_pl_not_english_fallback(monkeypatch):
    monkeypatch.setattr(
        "backend.app.platform.ai.sector_copy.load_company_sector_terms",
        lambda *a, **k: {
            "termSite": "Objekt",
            "termWorkers": "Einsatzkräfte",
            "_sector": "security",
        },
    )
    monkeypatch.setattr(
        "backend.app.platform.ai.context_builder.build_compact_context",
        lambda *a, **k: {
            "workersOnSite": 1,
            "pendingLeave": 0,
            "security": {},
            "intelligence": {"risk": {}, "attendance": {}},
            "emergency": {},
        },
    )
    monkeypatch.setattr(
        "backend.app.platform.ai.context_builder.deterministic_briefing",
        lambda *a, **k: "",
    )

    for lang, needle in (("tr", "Günlük"), ("fr", "Briefing"), ("pl", "Podsumowanie")):
        pulse = pulse_mod.build_operator_pulse(_FakeDb(), "cmp-1", lang=lang)
        labels = " ".join(str(r.get("label") or "") for r in pulse.get("recommendations") or [])
        assert needle in labels, f"{lang}: {labels}"
