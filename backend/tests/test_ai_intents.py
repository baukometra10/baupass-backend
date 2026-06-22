"""Intent router — contact and navigation shortcuts."""
from __future__ import annotations

import pytest

from backend import server
from backend.app.platform.ai.intents import try_intent_response


@pytest.fixture()
def db_with_company(client_and_db):
    _client, _db_path = client_and_db
    cid = "cmp-intent-test"
    with server.app.app_context():
        db = server.get_db()
        db.execute(
            """
            INSERT INTO companies (id, name, contact, plan, status, deleted_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (cid, "Intent Test GmbH", "kontakt@intent.test", "enterprise", "aktiv"),
        )
        db.commit()
    return cid


def test_contact_intent_returns_company_and_support(client_and_db, db_with_company):
    _client, _db_path = client_and_db
    with server.app.app_context():
        db = server.get_db()
        out = try_intent_response(db, db_with_company, "Wo sind meine Kontaktdaten?", lang="de")
    assert out is not None
    assert out["intent"] == "contact_help"
    assert "Firmen-Kontakt" in out["answer"]
    assert out.get("actions")


def test_navigation_intent_workers(client_and_db, db_with_company):
    _client, _db_path = client_and_db
    with server.app.app_context():
        db = server.get_db()
        out = try_intent_response(db, db_with_company, "Öffne die Mitarbeiter-Seite", lang="de")
    assert out is not None
    assert out["intent"] == "navigate"
    assert any("workers" in (a.get("url") or "") for a in out.get("actions") or [])


def test_analytical_workers_question_not_nav(client_and_db, db_with_company):
    _client, _db_path = client_and_db
    with server.app.app_context():
        db = server.get_db()
        out = try_intent_response(db, db_with_company, "Wer ist heute auf der Baustelle?", lang="de")
    assert out is None


def test_no_intent_for_random(client_and_db, db_with_company):
    _client, _db_path = client_and_db
    with server.app.app_context():
        db = server.get_db()
        assert try_intent_response(db, db_with_company, "xyzzy random nonsense 12345", lang="de") is None


def test_founder_intent_arabic(client_and_db, db_with_company):
    _client, _db_path = client_and_db
    with server.app.app_context():
        db = server.get_db()
        out = try_intent_response(
            db,
            db_with_company,
            "من الذي قام بتأسيس هذا النظام؟",
            lang="ar",
        )
    assert out is not None
    assert out["intent"] == "platform_founder"
    assert "Sherif Mohamed" in out["answer"]
    assert "Suppix Technologie UG" in out["answer"] or "WorkPass" in out["answer"]


def test_founder_intent_german(client_and_db, db_with_company):
    _client, _db_path = client_and_db
    with server.app.app_context():
        db = server.get_db()
        out = try_intent_response(
            db,
            db_with_company,
            "Wer hat WorkPass gegründet?",
            lang="de",
        )
    assert out is not None
    assert out["intent"] == "platform_founder"
    assert "Sherif Mohamed" in out["answer"]
    assert "baupass-control@outlook.de" in out["answer"]
