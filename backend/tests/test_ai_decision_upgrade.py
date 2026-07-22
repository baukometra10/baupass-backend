"""AI decision tools + action staging."""
from __future__ import annotations

import sqlite3
from contextlib import closing

from backend.app.platform.ai.actions import (
    approve_action,
    list_proposals,
    propose_action,
    reject_action,
)
from backend.app.platform.ai.agent_runner import _parse_decision_block
from backend.app.platform.ai.rag import search_knowledge
from backend.app.platform.ai.tools import TOOL_HANDLERS, run_tool
from backend.tests.test_outside_hours_employer_alert import _insert_gate_worker


def test_new_decision_tools_registered():
    for name in (
        "get_tomorrow_forecast",
        "get_repeated_late_workers",
        "get_outside_hours_attempts",
        "get_presence_summary",
        "browse_inbox",
    ):
        assert name in TOOL_HANDLERS


def test_tools_run_against_seeded_db(client_and_db):
    _client, db_path = client_and_db
    _insert_gate_worker(
        db_path,
        worker_id="wrk-ai-tools",
        card_id="NFC-AI-TOOLS",
        badge_id="BP-AI-TOOLS",
    )
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        for name in (
            "get_tomorrow_forecast",
            "get_repeated_late_workers",
            "get_outside_hours_attempts",
            "get_presence_summary",
            "browse_inbox",
        ):
            result = run_tool(db, "cmp-default", name, {})
            assert "error" not in result or result.get("error") != "unknown_tool"


def test_parse_decision_block():
    text = 'Hier die Lage.\nDECISION_JSON={"summary":"Staff Tor 2","recommendation":"shift","confidence":0.8,"rationale":"peak","evidence":[],"proposedActions":[]}'
    parsed = _parse_decision_block(text)
    assert parsed is not None
    assert parsed["summary"] == "Staff Tor 2"
    assert parsed["confidence"] == 0.8


def test_action_staging_flow(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        bad = propose_action(
            db,
            company_id="cmp-default",
            user_id="u1",
            action="delete_everything",
            params={},
        )
        assert bad["ok"] is False

        good = propose_action(
            db,
            company_id="cmp-default",
            user_id="u1",
            action="export_briefing_markdown",
            params={"text": "# hello"},
            rationale="export",
        )
        assert good["ok"] is True
        pid = good["proposal"]["id"]
        pending = list_proposals(db, company_id="cmp-default", status="pending")
        assert any(p["id"] == pid for p in pending)

        approved = approve_action(
            db,
            company_id="cmp-default",
            user_id="u1",
            proposal_id=pid,
            briefing_text="# hello",
        )
        assert approved["ok"] is True
        assert approved["status"] == "executed"

        other = propose_action(
            db,
            company_id="cmp-default",
            user_id="u1",
            action="export_briefing_markdown",
            params={"text": "x"},
        )
        rejected = reject_action(
            db,
            company_id="cmp-default",
            user_id="u1",
            proposal_id=other["proposal"]["id"],
            note="nope",
        )
        assert rejected["ok"] is True
        assert rejected["status"] == "rejected"


def test_company_memory_in_rag(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_company_memory (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'note',
                key TEXT,
                value TEXT NOT NULL,
                source TEXT DEFAULT 'ai',
                importance INTEGER NOT NULL DEFAULT 3,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT
            )
            """
        )
        db.execute(
            """
            INSERT INTO ai_company_memory
            (id, company_id, kind, key, value, source, importance, created_by, created_at, updated_at, expires_at)
            VALUES ('mem1', 'cmp-default', 'fact', 'gate_policy', 'Tor 2 opens at 06:30 for concrete pours', 'admin', 5, 'u1', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', NULL)
            """
        )
        db.commit()
        chunks = search_knowledge(db, "cmp-default", "concrete")
        assert any(c.get("source") == "company_memory" for c in chunks)
