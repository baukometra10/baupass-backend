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
    assert res.status_code in (200, 201)
    company = res.get_json().get("company") or {}
    company_id = company.get("id")
    worker_res = client.post(
        "/api/workers",
        json={
            "companyId": company_id,
            "firstName": "Voice",
            "lastName": "Worker",
            "insuranceNumber": "V123456789",
            "workerType": "worker",
            "role": "Monteur",
            "site": "Hof",
            "validUntil": "2028-12-31",
            "status": "aktiv",
            "photoData": "data:image/png;base64,AAA",
            "badgePin": "1234",
            "complianceSignatureData": "data:image/png;base64,AAA",
            "physicalCardId": "VOICE-CARD-1",
        },
        headers=headers,
    )
    assert worker_res.status_code == 201, worker_res.get_json()
    worker_payload = worker_res.get_json() or {}
    worker_id = worker_payload.get("id")
    badge_id = worker_payload.get("badgeId")
    assert worker_id and badge_id
    access = client.post(f"/api/workers/{worker_id}/app-access", headers=headers)
    assert access.status_code == 200, access.get_json()
    return company_id, worker_id, badge_id


def _worker_session_headers(client, badge_id):
    res = client.post(
        "/api/worker-app/login",
        json={"badgeId": badge_id, "badgePin": "1234", "platform": "android"},
    )
    assert res.status_code == 200, res.get_json()
    payload = res.get_json()
    token = payload.get("token") or payload.get("bearer")
    device_id = payload.get("deviceId") or payload.get("device_id") or "test-device"
    return {"Authorization": f"Bearer {token}", "X-Device-Id": device_id}


def test_admin_incoming_without_company_returns_200(client_and_db):
    """Background pollers must not get 400 when superadmin has no company scope."""
    client, _ = client_and_db
    headers = _admin_headers(client)
    res = client.get("/api/chat/calls/incoming", headers=headers)
    assert res.status_code == 200
    assert res.get_json().get("call") is None


def test_admin_can_start_voice_call(client_and_db):
    client, _ = client_and_db
    headers = _admin_headers(client)
    company_id, worker_id, badge_id = _create_company_and_worker(client, headers)

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
    company_id, worker_id, badge_id = _create_company_and_worker(client, headers)
    client.post("/api/superadmin/preview-session", json={"company_id": company_id}, headers=headers)

    start = client.post("/api/chat/calls", json={"worker_id": worker_id}, headers=headers)
    call_id = start.get_json()["call"]["id"]
    worker_headers = _worker_session_headers(client, badge_id)

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


def test_camera_and_image_signals_allowed(client_and_db):
    """In-call camera consent + photo share must be valid signal types."""
    from backend.app.platform.voice_calls.service import VoiceCallService, utc_now_iso

    client, _ = client_and_db
    with server.app.app_context():
        db = server.get_db()
        svc = VoiceCallService(db)
        call_id = "vc-cam-test-1"
        now = utc_now_iso()
        db.execute(
            """
            INSERT INTO chat_voice_calls
            (id, company_id, worker_id, caller_user_id, status, created_at, answered_at, initiated_by)
            VALUES (?, 'cmp-1', 'w-1', 'admin', 'accepted', ?, ?, 'admin')
            """,
            (call_id, now, now),
        )
        db.commit()

        intent = svc.add_signal(
            call_id,
            sender_role="admin",
            signal_type="camera_intent",
            payload={"enabled": True, "fromName": "Admin"},
        )
        assert intent.get("signalType") == "camera_intent"

        tiny = "data:image/jpeg;base64,/9j/4AAQ"
        image = svc.add_signal(
            call_id,
            sender_role="worker",
            signal_type="call_image",
            payload={"dataUrl": tiny, "fromName": "Worker"},
        )
        assert image.get("id")

        rows = db.execute(
            "SELECT signal_type FROM chat_voice_call_signals WHERE call_id = ? ORDER BY seq",
            (call_id,),
        ).fetchall()
        types = {row["signal_type"] for row in rows}
        assert "camera_intent" in types
        assert "call_image" in types

        try:
            svc.add_signal(
                call_id,
                sender_role="admin",
                signal_type="call_image",
                payload={"dataUrl": "data:image/jpeg;base64," + ("A" * 330000)},
            )
            assert False, "expected call_image_too_large"
        except ValueError as exc:
            assert str(exc) == "call_image_too_large"
    assert client is not None


def test_signal_pagination_keeps_same_timestamp_candidates(client_and_db, monkeypatch):
    """ICE bursts often share a second; since_id must not drop sibling rows."""
    from backend.app.platform.voice_calls import service as voice_service

    client, _ = client_and_db
    headers = _admin_headers(client)
    company_id, worker_id, badge_id = _create_company_and_worker(client, headers)
    client.post("/api/superadmin/preview-session", json={"company_id": company_id}, headers=headers)

    start = client.post("/api/chat/calls", json={"worker_id": worker_id}, headers=headers)
    call_id = start.get_json()["call"]["id"]
    worker_headers = _worker_session_headers(client, badge_id)
    accept = client.post(f"/api/worker-app/chat/calls/{call_id}/accept", headers=worker_headers)
    assert accept.status_code == 200, accept.get_json()

    # Freeze only for the ICE burst so sibling rows share one timestamp.
    fixed = "2026-07-19T12:00:00.000000Z"
    monkeypatch.setattr(voice_service, "utc_now_iso", lambda: fixed)

    for i in range(3):
        res = client.post(
            f"/api/chat/calls/{call_id}/signal",
            json={"type": "ice-candidate", "payload": {"candidate": f"cand-{i}", "sdpMid": "0", "sdpMLineIndex": 0}},
            headers=headers,
        )
        assert res.status_code == 200, res.get_json()

    first = client.get(f"/api/worker-app/chat/calls/{call_id}/signals", headers=worker_headers)
    assert first.status_code == 200
    batch = first.get_json().get("signals") or []
    assert len(batch) == 3
    since_id = batch[0]["id"]

    rest = client.get(
        f"/api/worker-app/chat/calls/{call_id}/signals?since_id={since_id}",
        headers=worker_headers,
    )
    assert rest.status_code == 200
    remaining = rest.get_json().get("signals") or []
    assert len(remaining) == 2
    assert {row["payload"]["candidate"] for row in remaining} == {"cand-1", "cand-2"}


def test_voice_call_history_and_worker_callback(client_and_db):
    client, _ = client_and_db
    headers = _admin_headers(client)
    company_id, worker_id, badge_id = _create_company_and_worker(client, headers)
    client.post("/api/superadmin/preview-session", json={"company_id": company_id}, headers=headers)

    start = client.post("/api/chat/calls", json={"worker_id": worker_id}, headers=headers)
    call_id = start.get_json()["call"]["id"]
    client.post(f"/api/chat/calls/{call_id}/end", json={"reason": "test"}, headers=headers)
    worker_headers = _worker_session_headers(client, badge_id)

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
    company_id, worker_id, badge_id = _create_company_and_worker(client, headers)
    client.post("/api/superadmin/preview-session", json={"company_id": company_id}, headers=headers)

    start = client.post("/api/chat/calls", json={"worker_id": worker_id}, headers=headers)
    call_id = start.get_json()["call"]["id"]
    worker_headers = _worker_session_headers(client, badge_id)

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
