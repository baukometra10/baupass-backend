"""Operator pulse — prioritized daily recommendations."""
from __future__ import annotations

import sqlite3
from contextlib import closing

from backend.app.platform.ai.actions import ALLOWED_EXECUTE, execute_action
from backend.app.platform.ai.operator_pulse import build_operator_pulse
from backend.app.platform.ai.operator_tasks import try_operator_task


def test_pulse_returns_recommendations(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        pulse = build_operator_pulse(db, "cmp-default", lang="de")
        assert pulse["companyId"] == "cmp-default"
        assert isinstance(pulse["recommendations"], list)
        assert len(pulse["recommendations"]) >= 2
        assert "snapshot" in pulse
        assert "urgency" in pulse


def test_prioritize_intent(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        hit = try_operator_task(
            db,
            "cmp-default",
            "Was soll ich heute priorisieren?",
            role="company-admin",
            lang="de",
        )
        assert hit is not None
        assert hit.get("intent") == "operator_prioritize"
        assert hit.get("ok") is True


def test_export_ops_snapshot_action(client_and_db):
    assert "export_ops_snapshot" in ALLOWED_EXECUTE
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        result = execute_action(
            db,
            company_id="cmp-default",
            user_id="admin-1",
            action="export_ops_snapshot",
            params={"lang": "en"},
        )
        assert result.get("ok") is True
        assert result.get("format") == "markdown"
        assert "Operations briefing" in (result.get("content") or "") or "briefing" in (
            result.get("content") or ""
        ).lower()
