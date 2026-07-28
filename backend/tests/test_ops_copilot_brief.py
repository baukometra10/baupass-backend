"""Copilot deterministic answers use daily-brief Chat/HR KPIs."""
from __future__ import annotations


def test_deterministic_qa_lage_includes_chat_and_hr():
    from backend.app.platform.physical_operations.copilot import _deterministic_qa

    ctx = {
        "workersOnSite": 3,
        "pendingLeave": 2,
        "security": {"openFindings": 1},
        "dailyBrief": {
            "attendance": {
                "onSite": 3,
                "lateToday": 1,
                "missingExpected": 2,
                "outsideHoursAttemptsToday": 0,
            },
            "security": {"totalOpen": 1, "openCameraEscalations": 0, "openSecurityAlerts": 1},
            "chat": {
                "missedCallsOpen": 1,
                "callbackRequestsOpen": 1,
                "totalOpen": 2,
                "items": [{"kind": "callback_requested", "workerName": "Vera Ruft"}],
            },
            "hr": {
                "pendingLeave": 2,
                "expiringDocuments": 1,
                "inReviewDocuments": 1,
                "totalOpen": 4,
                "items": [{"kind": "docs_review", "docTitle": "SU Q3"}],
            },
        },
    }
    lage = _deterministic_qa(ctx, "Fasse die aktuelle Lage zusammen")
    assert lage.get("source") == "daily_brief"
    answer = str(lage.get("answer") or "")
    assert "Chat/Anrufe 2" in answer
    assert "HR 4" in answer
    assert "Prüfung 1" in answer
    assert "fehlt 2" in answer

    chat = _deterministic_qa(ctx, "Welche Chat-/Anruf-Nachzüge sind offen (verpasst, Rückruf)?")
    assert chat.get("source") == "daily_brief.chat"
    assert "Rückruf" in str(chat.get("answer") or "")
    assert "kein Auto-Dial" in str(chat.get("answer") or "").lower() or "Kein Auto-Dial" in str(
        chat.get("answer") or ""
    )

    hr = _deterministic_qa(ctx, "Welche Urlaubsanträge sind offen und welche Dokumente laufen ab?")
    assert hr.get("source") == "daily_brief.hr"
    assert "Urlaub 2" in str(hr.get("answer") or "")
    assert "Docs ablaufend 1" in str(hr.get("answer") or "")
    assert "in Prüfung 1" in str(hr.get("answer") or "")
    assert "SU Q3" in str(hr.get("answer") or "")


def test_copilot_context_includes_daily_brief(client_and_db):
    client, _db_path = client_and_db
    login = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.get_json()['token']}"}
    created = client.post(
        "/api/companies",
        json={
            "name": "CopilotBriefCo",
            "contact": "x",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 0,
        },
        headers=headers,
    )
    assert created.status_code in (200, 201)
    payload = created.get_json() or {}
    cid = str((payload.get("company") or {}).get("id") or payload.get("id") or "")
    assert cid

    r = client.post(
        "/api/ops-os/copilot",
        headers=headers,
        json={"question": "Lage heute Übersicht", "company_id": cid},
    )
    assert r.status_code == 200, r.get_json()
    body = r.get_json() or {}
    # Without OpenAI key: deterministicAnswers; with key: answer/contextSummary.
    det = body.get("deterministicAnswers") or {}
    answer = str(body.get("answer") or det.get("answer") or "")
    assert answer
    assert "Lage" in answer or "vor Ort" in answer or "Chat" in answer or "HR" in answer
    ctx = body.get("context") or {}
    if ctx:
        assert "dailyBrief" in ctx
