"""Operator pulse — surface context + morning dispatch text."""
from __future__ import annotations

import sqlite3
from contextlib import closing

from backend.app.platform.ai.operator_pulse import (
    build_operator_pulse,
    format_morning_dispatch,
    normalize_surface,
)
from backend.app.platform.ai.scheduler import build_company_morning_dispatch


def test_normalize_surface_from_path_and_tab():
    assert normalize_surface(path="/admin-v2/contracts.html") == "contracts"
    assert normalize_surface(path="/admin-v2/docs.html") == "docs"
    assert normalize_surface(tab="workers") == "workers"
    assert normalize_surface(path="/enterprise-hub.html") == "hub"
    assert normalize_surface("operations") == "operations"


def test_contracts_surface_boosts_nav(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        pulse = build_operator_pulse(
            db, "cmp-default", lang="de", surface="contracts", path="/admin-v2/contracts.html"
        )
        assert pulse["surface"] == "contracts"
        ids = [r["id"] for r in pulse["recommendations"]]
        assert "contracts_nav" in ids
        # Nav recommendation should rank near the top on contracts surface.
        assert ids.index("contracts_nav") <= 3


def test_workers_surface_includes_plan_late(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        pulse = build_operator_pulse(db, "cmp-default", lang="en", surface="workers", tab="workers")
        ids = {r["id"] for r in pulse["recommendations"]}
        assert "plan" in ids or "onsite" in ids


def test_morning_dispatch_contains_priorities(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        pulse = build_operator_pulse(db, "cmp-default", lang="de")
        text = format_morning_dispatch(pulse, company_name="Demo GmbH")
        assert "Morgen-Betriebs-Pulse" in text or "Prioritäten" in text
        assert "Demo GmbH" in text


def test_build_company_morning_dispatch_body(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        payload = build_company_morning_dispatch(
            db,
            "cmp-default",
            company_name="Demo",
            lang="en",
            include_llm=False,
        )
        assert payload["companyId"] == "cmp-default"
        assert "Morning operations pulse" in payload["body"]
        assert payload["hasLlm"] is False
