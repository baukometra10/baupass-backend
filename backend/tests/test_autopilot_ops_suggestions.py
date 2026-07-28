"""Soft hints for missing expected workers + open security (no auto-dial)."""
from __future__ import annotations

import json
from pathlib import Path

import sqlite3


def _superadmin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def _create_company(client, headers, name: str) -> str:
    response = client.post(
        "/api/companies",
        json={
            "name": name,
            "contact": "x",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 0,
        },
        headers=headers,
    )
    assert response.status_code in (200, 201)
    payload = response.get_json() or {}
    company = payload.get("company") or {}
    return str(company.get("id") or payload.get("id") or "")


def _open_db(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def test_autopilot_suggests_missing_and_security_without_autodial(client_and_db, monkeypatch):
    from backend.app.platform.autopilot.runner import run_company_autopilot
    from backend.app.platform.autopilot.settings import save_settings

    client, db_path = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "AutoMissSecCo")

    def fake_attendance(_db, _cid):
        return {
            "missingExpected": 2,
            "missingWorkers": [{"name": "Max Fehlt"}, {"name": "Sara Weg"}],
        }

    def fake_security(_db, _cid):
        return {
            "openSecurityAlerts": 1,
            "openCameraEscalations": 1,
            "totalOpen": 2,
        }

    monkeypatch.setattr(
        "backend.app.platform.physical_operations.daily_brief.build_attendance_brief",
        fake_attendance,
    )
    monkeypatch.setattr(
        "backend.app.platform.physical_operations.daily_brief.build_security_brief",
        fake_security,
    )

    db = _open_db(db_path)
    try:
        save_settings(
            db,
            cid,
            {
                "autoSuggestMissingExpected": True,
                "autoSuggestOpenSecurity": True,
                "autoSuggestPendingLeave": False,
                "autoSuggestDocsReview": False,
                "autoNotifyDocExpiry": False,
                "autoDailySecurityScan": False,
                "autoAckInfoAlerts": False,
                "autoInboxBulkDocPush": False,
                "autoSeedAutomationRules": False,
                "autoEnsureScheduledReport": False,
                "autoPrepareNextMonthDeployment": False,
            },
            actor="test",
        )
        summary = run_company_autopilot(db, cid)
    finally:
        db.close()

    assert summary.get("ok") is True
    miss = summary.get("missingSuggest") or {}
    sec = summary.get("securityOpenSuggest") or {}
    assert miss.get("ok") is True
    assert int(miss.get("missingExpected") or 0) == 2
    assert sec.get("ok") is True
    assert int(sec.get("totalOpen") or 0) == 2

    db = _open_db(db_path)
    try:
        alerts = db.execute(
            """
            SELECT code, details FROM system_alerts
            WHERE code IN ('autopilot.missing_expected', 'autopilot.security_open')
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchall()
        codes = {str(a["code"]) for a in alerts}
        assert "autopilot.missing_expected" in codes
        assert "autopilot.security_open" in codes
        for a in alerts:
            details = json.loads(a["details"] or "{}")
            assert details.get("autoDial") is False
    finally:
        db.close()
