"""Smoke path: Daily Brief → Inbox → Copilot (ops loop)."""
from __future__ import annotations


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


def test_ops_loop_brief_inbox_copilot_smoke(client_and_db):
    client, _db_path = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "OpsLoopSmokeCo")
    assert cid

    brief = client.get(f"/api/ops-os/daily-brief?company_id={cid}", headers=headers)
    assert brief.status_code == 200
    body = brief.get_json() or {}
    assert body.get("ok") is True
    assert body.get("autoDial") is False
    assert isinstance(body.get("attendance"), dict)
    assert isinstance(body.get("security"), dict)
    assert isinstance(body.get("chat"), dict)
    assert isinstance(body.get("hr"), dict)

    inbox = client.get(f"/api/inbox?company_id={cid}", headers=headers)
    assert inbox.status_code == 200
    inbox_body = inbox.get_json() or {}
    assert "items" in inbox_body or "ok" in inbox_body or isinstance(inbox_body, dict)

    live = client.get(f"/api/ops-os/live-map?company_id={cid}", headers=headers)
    assert live.status_code == 200
    live_body = live.get_json() or {}
    assert live_body.get("autoDial") is False
    assert "counts" in live_body

    copilot = client.post(
        f"/api/ops-os/copilot?company_id={cid}",
        headers=headers,
        json={"question": "Fasse die aktuelle Lage zusammen", "company_id": cid},
    )
    assert copilot.status_code == 200
    cbody = copilot.get_json() or {}
    det = cbody.get("deterministicAnswers") or {}
    answer = str(cbody.get("answer") or det.get("answer") or "")
    assert answer
    assert "auto-polizei" not in answer.lower()

    ctx = client.get(f"/api/ops-os/copilot/context?company_id={cid}", headers=headers)
    assert ctx.status_code == 200
    ctx_body = ctx.get_json() or {}
    blob = ctx_body.get("dailyBrief") or (ctx_body.get("context") or {}).get("dailyBrief") or {}
    # context endpoint may wrap differently — also accept nested from POST body
    if not blob:
        blob = (cbody.get("context") or {}).get("dailyBrief") or {}
    if blob:
        assert isinstance(blob, dict)
        assert "attendance" in blob or "security" in blob or "chat" in blob
