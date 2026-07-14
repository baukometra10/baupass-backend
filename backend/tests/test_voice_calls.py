"""Voice call signaling tests."""
from __future__ import annotations

from backend import server


def _admin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def _create_company_and_worker(client, headers):
    res = client.post(
        "/api/companies",
        json={
            "name": "VoiceCallCo",
            "contact": "boss",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 0,
        },
        headers=headers,
    )
    assert res.status_code == 200
    company = res.get_json().get("company") or {}
    company_id = company.get("id")
    workers = client.get(f"/api/companies/{company_id}/workers", headers=headers)
    worker_rows = workers.get_json().get("workers") or []
    assert worker_rows
    return company_id, worker_rows[0]["id"]


def _worker_session_headers(client, worker_id):
    res = client.post(
        "/api/worker-app/login",
        json={"workerId": worker_id, "pin": "1234", "platform": "android"},
    )
    assert res.status_code == 200
    payload = res.get_json()
    token = payload.get("token") or payload.get("bearer")
    device_id = payload.get("deviceId") or payload.get("device_id") or "test-device"
    return {"Authorization": f"Bearer {token}", "X-Device-Id": device_id}


def test_admin_can_start_voice_call(client_and_db):
    client, _ = client_and_db
    headers = _admin_headers(client)
    company_id, worker_id = _create_company_and_worker(client, headers)

    preview = client.post(
        "/api/superadmin/preview-session",
        json={"company_id": company_id},
        headers=headers,
    )
    assert preview.status_code == 200

    res = client.post(
        "/api/chat/calls",
        json={"worker_id": worker_id},
        headers=headers,
    )
    assert res.status_code == 200
    call = res.get_json().get("call") or {}
    assert call.get("id")
    assert call.get("status") == "ringing"
    assert call.get("workerId") == worker_id
    assert isinstance(call.get("iceServers"), list)


def test_worker_can_accept_and_exchange_signals(client_and_db):
    client, _ = client_and_db
    headers = _admin_headers(client)
    company_id, worker_id = _create_company_and_worker(client, headers)
    client.post("/api/superadmin/preview-session", json={"company_id": company_id}, headers=headers)

    start = client.post("/api/chat/calls", json={"worker_id": worker_id}, headers=headers)
    call_id = start.get_json()["call"]["id"]
    worker_headers = _worker_session_headers(client, worker_id)

    incoming = client.get("/api/worker-app/chat/calls/incoming", headers=worker_headers)
    assert incoming.status_code == 200
    assert (incoming.get_json().get("call") or {}).get("id") == call_id

    accepted = client.post(f"/api/worker-app/chat/calls/{call_id}/accept", headers=worker_headers)
    assert accepted.status_code == 200
    assert accepted.get_json()["call"]["status"] == "accepted"

    offer = client.post(
        f"/api/chat/calls/{call_id}/signal",
        json={"type": "offer", "payload": {"type": "offer", "sdp": "v=0"}},
        headers=headers,
    )
    assert offer.status_code == 200

    signals = client.get(f"/api/worker-app/chat/calls/{call_id}/signals", headers=worker_headers)
    assert signals.status_code == 200
    rows = signals.get_json().get("signals") or []
    assert len(rows) == 1
    assert rows[0]["signalType"] == "offer"

    end = client.post(f"/api/chat/calls/{call_id}/end", json={"reason": "test"}, headers=headers)
    assert end.status_code == 200
    assert end.get_json()["call"]["status"] == "ended"

    thread = client.post(
        "/api/chat/threads",
        json={"worker_id": worker_id, "subject": "general"},
        headers=headers,
    )
    assert thread.status_code == 200
    thread_id = thread.get_json().get("threadId")
    messages = client.get(f"/api/chat/threads/{thread_id}?company_id={company_id}", headers=headers)
    assert messages.status_code == 200
    rows = messages.get_json().get("messages") or []
    assert any("@voice-call|" in str(row.get("body") or "") for row in rows)


def test_voice_call_history_and_worker_callback(client_and_db):
    client, _ = client_and_db
    headers = _admin_headers(client)
    company_id, worker_id = _create_company_and_worker(client, headers)
    client.post("/api/superadmin/preview-session", json={"company_id": company_id}, headers=headers)

    start = client.post("/api/chat/calls", json={"worker_id": worker_id}, headers=headers)
    call_id = start.get_json()["call"]["id"]
    client.post(f"/api/chat/calls/{call_id}/end", json={"reason": "test"}, headers=headers)
    worker_headers = _worker_session_headers(client, worker_id)

    history = client.get(f"/api/chat/calls/history?worker_id={worker_id}", headers=headers)
    assert history.status_code == 200
    payload = history.get_json()
    assert isinstance(payload.get("calls"), list)
    assert payload["calls"]

    worker_history = client.get("/api/worker-app/chat/calls/history", headers=worker_headers)
    assert worker_history.status_code == 200
    assert worker_history.get_json().get("calls")

    callback = client.post(
        "/api/worker-app/chat/calls/callback-request",
        json={"call_id": call_id},
        headers=worker_headers,
    )
    assert callback.status_code == 200
    assert callback.get_json().get("ok") is True


def test_worker_can_fetch_call_by_id(client_and_db):
    client, _ = client_and_db
    headers = _admin_headers(client)
    company_id, worker_id = _create_company_and_worker(client, headers)
    client.post("/api/superadmin/preview-session", json={"company_id": company_id}, headers=headers)

    start = client.post("/api/chat/calls", json={"worker_id": worker_id}, headers=headers)
    call_id = start.get_json()["call"]["id"]
    worker_headers = _worker_session_headers(client, worker_id)

    fetched = client.get(f"/api/worker-app/chat/calls/{call_id}", headers=worker_headers)
    assert fetched.status_code == 200
    call = fetched.get_json().get("call") or {}
    assert call.get("id") == call_id
    assert call.get("status") == "ringing"
    assert isinstance(call.get("iceServers"), list)


def test_voice_call_push_deeplink_includes_call_id():
    from backend.app.platform.push.deeplinks import push_data_payload

    payload = push_data_payload(tag="voice-call", worker_id="wrk-1", extra={"callId": "vc-test-1"})
    assert payload["tag"] == "voice-call"
    assert "callId=vc-test-1" in payload["route"]
    assert payload["callId"] == "vc-test-1"


def test_ice_servers_diagnostics_turn_configured(monkeypatch):
    from backend.app.platform.voice_calls import service as voice_service

    monkeypatch.delenv("SUPPIX_ICE_SERVERS_JSON", raising=False)
    monkeypatch.delenv("BAUPASS_ICE_SERVERS_JSON", raising=False)
    monkeypatch.setenv("SUPPIX_TURN_URL", "turn:global.relay.metered.ca:443?transport=tcp")
    monkeypatch.setenv("SUPPIX_TURN_USERNAME", "user")
    monkeypatch.setenv("SUPPIX_TURN_PASSWORD", "pass")
    diag = voice_service.ice_servers_diagnostics()
    assert diag["turnConfigured"] is True
    assert diag["primaryTurnUrl"] == "turn:global.relay.metered.ca:443?transport=tcp"
    assert any("relay.metered.ca" in u for u in diag["urls"])


def test_ice_servers_prefers_suppix_turn_over_baupass(monkeypatch):
    from backend.app.platform.voice_calls import service as voice_service

    monkeypatch.delenv("SUPPIX_ICE_SERVERS_JSON", raising=False)
    monkeypatch.setenv("BAUPASS_TURN_URL", "turn:old.example.com:3478")
    monkeypatch.setenv("SUPPIX_TURN_URL", "turn:global.relay.metered.ca:443?transport=tcp")
    monkeypatch.setenv("SUPPIX_TURN_USERNAME", "user")
    monkeypatch.setenv("SUPPIX_TURN_PASSWORD", "pass")
    diag = voice_service.ice_servers_diagnostics()
    assert diag["primaryTurnUrl"] == "turn:global.relay.metered.ca:443?transport=tcp"
