"""Sector vocabulary, operator memory, and morning dispatch sector labels."""
from __future__ import annotations

from backend.app.platform.ai.operator_memory import get_memory, save_memory
from backend.app.platform.ai.operator_pulse import format_morning_dispatch
from backend.app.platform.ai.sector_copy import apply_sector_text, sector_vocab


class _FakeDb:
    def __init__(self):
        self.rows = {}

    def execute(self, sql, params=None):
        sql_l = " ".join(str(sql).lower().split())
        if sql_l.startswith("create table"):
            return self
        if "select" in sql_l and "company_ai_operator_memory" in sql_l:
            raw = self.rows.get(params[0])
            if not raw:
                return _Result(None)
            return _Result({"memory_json": raw, "updated_at": "t"})
        if "insert" in sql_l and "company_ai_operator_memory" in sql_l:
            self.rows[params[0]] = params[1]
            return self
        return self

    def commit(self):
        return None


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


def test_apply_sector_text_replaces_baustelle():
    out = apply_sector_text("Wer ist auf der Baustelle?", workers="Einsatzkräfte", site="Objekt", lang="de")
    assert "Baustelle" not in out
    assert "Objekt" in out


def test_sector_vocab_security_style():
    workers, site, _gate = sector_vocab(
        {"termWorkers": "Einsatzkräfte", "termSite": "Objekt"},
        "de",
    )
    assert workers == "Einsatzkräfte"
    assert site == "Objekt"


def test_morning_dispatch_uses_sector_site():
    body = format_morning_dispatch(
        {
            "lang": "de",
            "sectorTerms": {"termSite": "Objekt", "termWorkers": "Einsatzkräfte"},
            "snapshot": {
                "workersOnSite": 3,
                "openSecurityFindings": 0,
                "pendingLeave": 0,
                "expiredDocuments": 0,
                "riskLevel": "low",
            },
            "recommendations": [],
        },
        company_name="SecurCo",
    )
    assert "Objekt" in body
    assert "Vor Ort" not in body


def test_operator_memory_remembers_prompt():
    db = _FakeDb()
    mem = save_memory(db, "cmp-1", {"rememberPrompt": "Erinnerung wie gestern", "preferredLang": "ar"})
    assert mem["preferredLang"] == "ar"
    assert mem["recentPrompts"][0] == "Erinnerung wie gestern"
    assert "Erinnerung" in mem["lastReminderPrompt"]
    again = get_memory(db, "cmp-1")
    assert again["preferredLang"] == "ar"
