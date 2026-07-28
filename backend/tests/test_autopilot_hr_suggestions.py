"""Autopilot soft suggestions for leave + docs review (no auto-approve)."""
from __future__ import annotations

import json
from datetime import date, timedelta
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


def test_autopilot_suggests_leave_and_docs_without_approve(client_and_db):
    from backend.app.platform.autopilot.runner import run_company_autopilot
    from backend.app.platform.autopilot.settings import save_settings

    client, db_path = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "AutoSuggestCo")
    created = client.post(
        f"/api/workers?company_id={cid}",
        headers=headers,
        json={
            "companyId": cid,
            "firstName": "Alex",
            "lastName": "Leave",
            "insuranceNumber": "INS-AP-SUG-1",
            "workerType": "worker",
            "role": "Monteur",
            "site": "Nordtor",
            "validUntil": "2026-12-31",
            "status": "aktiv",
            "photoData": "data:image/png;base64,AAA",
            "badgePin": "1234",
            "complianceSignatureData": "data:image/png;base64,AAA",
            "physicalCardId": f"CARD-AP-SUG-{cid[:8]}",
        },
    )
    assert created.status_code in (200, 201), created.get_json()
    wid = str((created.get_json() or {}).get("id") or "")
    assert wid

    today = date.today()
    leave_id = f"lv-ap-{cid[:8]}"
    edoc_id = f"edoc-ap-{cid[:8]}"
    db = _open_db(db_path)
    try:
        db.execute(
            """
            INSERT INTO leave_requests
            (id, worker_id, company_id, type, start_date, end_date, days_count, note, status, created_at)
            VALUES (?, ?, ?, 'urlaub', ?, ?, 3, '', 'ausstehend', datetime('now'))
            """,
            (leave_id, wid, cid, today.isoformat(), (today + timedelta(days=2)).isoformat()),
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS editor_documents (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                title TEXT NOT NULL DEFAULT 'Unbenannt',
                mode TEXT NOT NULL DEFAULT 'general',
                status TEXT NOT NULL DEFAULT 'draft',
                content_json TEXT NOT NULL DEFAULT '',
                content_html TEXT NOT NULL DEFAULT '',
                content_text TEXT NOT NULL DEFAULT '',
                worker_id TEXT,
                contract_id TEXT,
                created_by_user_id TEXT,
                updated_by_user_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            INSERT INTO editor_documents
            (id, company_id, title, mode, status, created_at, updated_at)
            VALUES (?, ?, 'Vertrag Entwurf', 'general', 'in_review', datetime('now'), datetime('now'))
            """,
            (edoc_id, cid),
        )
        db.commit()
        save_settings(
            db,
            cid,
            {
                "autoSuggestPendingLeave": True,
                "autoSuggestDocsReview": True,
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
    leave = summary.get("leaveSuggest") or {}
    docs = summary.get("docsReviewSuggest") or {}
    assert leave.get("ok") is True
    assert int(leave.get("pendingLeave") or 0) >= 1
    assert docs.get("ok") is True
    assert int(docs.get("inReviewDocuments") or 0) >= 1

    # Leave still pending — no auto-approve
    db = _open_db(db_path)
    try:
        st = db.execute("SELECT status FROM leave_requests WHERE id = ?", (leave_id,)).fetchone()
        assert str(st["status"]) in ("pending", "ausstehend")
        doc_st = db.execute("SELECT status FROM editor_documents WHERE id = ?", (edoc_id,)).fetchone()
        assert str(doc_st["status"]) == "in_review"
        alerts = db.execute(
            """
            SELECT code, message, details FROM system_alerts
            WHERE code IN ('autopilot.leave_queue', 'autopilot.docs_review')
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchall()
        codes = {str(a["code"]) for a in alerts}
        assert "autopilot.leave_queue" in codes
        assert "autopilot.docs_review" in codes
        for a in alerts:
            details = json.loads(a["details"] or "{}")
            assert details.get("autoApprove") is False
    finally:
        db.close()

    inbox = client.get(f"/api/inbox?company_id={cid}&source=system", headers=headers)
    assert inbox.status_code == 200
    items = (inbox.get_json() or {}).get("items") or []
    codes_in_inbox = {str(it.get("code") or "") for it in items}
    assert "autopilot.leave_queue" in codes_in_inbox or any(
        "Urlaub" in str(it.get("title") or it.get("message") or "") for it in items
    )
    assert "autopilot.docs_review" in codes_in_inbox or any(
        "Prüfung" in str(it.get("title") or it.get("message") or "") for it in items
    )
