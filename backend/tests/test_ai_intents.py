"""Intent router — contact and navigation shortcuts."""
from __future__ import annotations

import pytest

from backend import server
from backend.app.platform.ai.intents import try_intent_response


@pytest.fixture()
def db_with_company(client_and_db):
    _client, _db_path = client_and_db
    db = server.get_db()
    cid = "cmp-intent-test"
    db.execute(
        """
        INSERT INTO companies (id, name, contact, plan, status, deleted_at)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        (cid, "Intent Test GmbH", "kontakt@intent.test", "enterprise", "aktiv"),
    )
    db.commit()
    return db, cid


def test_contact_intent_returns_company_and_support(db_with_company):
    db, cid = db_with_company
    out = try_intent_response(db, cid, "Wo sind meine Kontaktdaten?", lang="de")
    assert out is not None
    assert out["intent"] == "contact_help"
    assert "Firmen-Kontakt" in out["answer"]
    assert out.get("actions")


def test_navigation_intent_workers(db_with_company):
    db, cid = db_with_company
    out = try_intent_response(db, cid, "Zeige mir die Mitarbeiter", lang="de")
    assert out is not None
    assert out["intent"] == "navigate"
    assert any("workers" in (a.get("url") or "") for a in out.get("actions") or [])


def test_no_intent_for_random(db_with_company):
    db, cid = db_with_company
    assert try_intent_response(db, cid, "xyzzy random nonsense 12345", lang="de") is None
