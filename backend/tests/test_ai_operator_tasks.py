"""Operator task intents — real confirmable actions."""
from __future__ import annotations

import sqlite3
from contextlib import closing

from backend.app.platform.ai.operator_tasks import try_operator_task
from backend.tests.test_outside_hours_employer_alert import _insert_gate_worker


def test_prepare_deployment_intent(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        hit = try_operator_task(
            db,
            "cmp-default",
            "Erstell mir einen Einsatzplan",
            role="company-admin",
            lang="de",
        )
        assert hit is not None
        assert hit.get("intent") == "operator_prepare_deployment"
        actions = hit.get("suggestedActions") or []
        assert any(a.get("action") == "prepare_deployment_month" for a in actions)


def test_onsite_intent(client_and_db):
    _client, db_path = client_and_db
    _insert_gate_worker(db_path, worker_id="wrk-op-1", card_id="NFC-OP-1", badge_id="BP-OP-1")
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        hit = try_operator_task(
            db,
            "cmp-default",
            "Wer ist vor Ort?",
            role="company-admin",
            lang="de",
        )
        assert hit is not None
        assert hit.get("intent") == "operator_onsite"


def test_onsite_intent_french(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        hit = try_operator_task(
            db,
            "cmp-default",
            "Qui est sur site aujourd'hui ?",
            role="company-admin",
            lang="fr",
        )
        assert hit is not None
        assert hit.get("intent") == "operator_onsite"


def test_briefing_intent_spanish(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        hit = try_operator_task(
            db,
            "cmp-default",
            "Muéstrame el resumen diario",
            role="company-admin",
            lang="es",
        )
        assert hit is not None
        assert hit.get("intent") == "operator_daily_briefing"


def test_expired_docs_intent(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        hit = try_operator_task(
            db,
            "cmp-default",
            "Abgelaufene Dokumente erinnern",
            role="company-admin",
            lang="de",
        )
        assert hit is not None
        assert hit.get("intent") == "operator_expired_docs"
        assert any(
            a.get("action") == "remind_expired_documents"
            for a in (hit.get("suggestedActions") or [])
        )


def test_leave_reject_intent(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        db.execute(
            """
            INSERT INTO leave_requests (id, company_id, worker_id, start_date, end_date, type, status, created_at)
            VALUES ('leave-op-1', 'cmp-default', 'wrk-missing', '2026-08-01', '2026-08-05', 'Urlaub', 'ausstehend', datetime('now'))
            """
        )
        db.commit()
        hit = try_operator_task(
            db,
            "cmp-default",
            "Urlaubsantrag ablehnen",
            role="company-admin",
            lang="de",
        )
        assert hit is not None
        assert hit.get("intent") == "operator_leave_queue"
        assert any(
            a.get("action") == "reject_leave_request"
            for a in (hit.get("suggestedActions") or [])
        )


def test_broadcast_intent(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        hit = try_operator_task(
            db,
            "cmp-default",
            "Mitteilung an alle: Bitte Helme tragen",
            role="company-admin",
            lang="de",
        )
        assert hit is not None
        assert hit.get("intent") == "operator_broadcast"
        assert any(
            a.get("action") == "broadcast_worker_message"
            for a in (hit.get("suggestedActions") or [])
        )


def test_new_actions_allowed():
    from backend.app.platform.ai.actions import ALLOWED_EXECUTE

    for name in (
        "remind_expired_documents",
        "remind_late_workers",
        "resolve_open_security_alerts",
        "ack_open_system_alerts",
        "broadcast_worker_message",
    ):
        assert name in ALLOWED_EXECUTE


def test_worker_role_ignored(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        hit = try_operator_task(
            db,
            "cmp-default",
            "Erstell mir einen Einsatzplan",
            role="worker",
            lang="de",
        )
        assert hit is None


def test_daily_briefing_intent(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        hit = try_operator_task(
            db,
            "cmp-default",
            "Was ist heute wichtig? Tageslage",
            role="company-admin",
            lang="de",
        )
        assert hit is not None
        assert hit.get("intent") == "operator_daily_briefing"


def test_open_contracts_intent(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        hit = try_operator_task(
            db,
            "cmp-default",
            "Öffne Verträge",
            role="company-admin",
            lang="de",
        )
        assert hit is not None
        assert hit.get("intent") == "operator_open_contracts"


def test_find_worker_intent(client_and_db):
    _client, db_path = client_and_db
    _insert_gate_worker(db_path, worker_id="wrk-find-1", card_id="NFC-F1", badge_id="BP-F1")
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        # Ensure searchable name exists for fixture worker.
        db.execute(
            "UPDATE workers SET first_name = ?, last_name = ? WHERE id = ?",
            ("Ahmed", "Test", "wrk-find-1"),
        )
        db.commit()
        hit = try_operator_task(
            db,
            "cmp-default",
            "Finde Ahmed",
            role="company-admin",
            lang="de",
        )
        assert hit is not None
        assert hit.get("intent") == "operator_find_worker"


def test_presence_intent(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        hit = try_operator_task(
            db,
            "cmp-default",
            "Anwesenheitsübersicht zeigen",
            role="company-admin",
            lang="de",
        )
        assert hit is not None
        assert hit.get("intent") == "operator_presence"


def test_navigate_contracts_all_ui_langs(client_and_db):
    from backend.app.platform.ai.langs import SUPPORTED_UI_LANGS
    from backend.app.platform.ai.operator_i18n import NAV_COPY

    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        for lang in sorted(SUPPORTED_UI_LANGS):
            hit = try_operator_task(
                db,
                "cmp-default",
                "Öffne Verträge",
                role="company-admin",
                lang=lang,
            )
            assert hit is not None
            assert hit.get("intent") == "operator_open_contracts"
            assert hit.get("answer") == NAV_COPY["contracts"][lang]
            action = (hit.get("actions") or [{}])[0]
            assert action.get("labels", {}).get(lang)


def test_operator_i18n_packs_complete():
    from backend.app.platform.ai.langs import SUPPORTED_UI_LANGS
    from backend.app.platform.ai.operator_i18n import NAV_COPY, NAV_LABELS

    for key, pack in {**NAV_COPY, **{f"lbl:{k}": v for k, v in NAV_LABELS.items()}}.items():
        assert SUPPORTED_UI_LANGS <= set(pack), key
