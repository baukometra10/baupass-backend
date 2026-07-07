"""Tests for enforced E2E chat policy."""
from __future__ import annotations

import base64
import json


def _fake_envelope() -> str:
    payload = {
        "e2e": True,
        "v": 1,
        "alg": "X25519-AES-GCM",
        "epk": base64.b64encode(b"\x30" + b"\x01" * 40).decode("ascii"),
        "iv": base64.b64encode(b"\x00" * 12).decode("ascii"),
        "ct": base64.b64encode(b"cipher").decode("ascii"),
    }
    return json.dumps(payload)


def _fake_spki_b64() -> str:
    return base64.b64encode(b"\x30" + b"\x00" * 40).decode("ascii")


def test_e2e_envelope_detection():
    from backend.app.platform.security.e2e_envelope import is_e2e_envelope

    assert is_e2e_envelope(_fake_envelope()) is True
    assert is_e2e_envelope("hello") is False
    multi = json.dumps({
        "e2e": True,
        "v": 1,
        "multi": True,
        "envelopes": [json.loads(_fake_envelope()), json.loads(_fake_envelope())],
    })
    assert is_e2e_envelope(multi) is True


def test_chat_allows_plaintext_until_both_keys_registered(client_and_db, monkeypatch):
    from backend.app.platform.security import e2e_policy

    monkeypatch.setattr(e2e_policy, "e2e_chat_required", lambda: True)
    client, db_path = client_and_db
    from backend.tests.test_e2e_identity_routes import (
        _create_company,
        _superadmin_headers,
        _worker_session_headers,
    )

    admin_headers = _superadmin_headers(client)
    company_id = _create_company(client, admin_headers, "E2EPolicyCo")
    worker_headers, worker_id = _worker_session_headers(client, db_path, company_id)
    thread = client.post(
        "/api/worker-app/chat/threads",
        headers=worker_headers,
        json={"subject": "general"},
    )
    assert thread.status_code == 200
    thread_id = thread.get_json().get("threadId") or ""
    assert thread_id

    allowed = client.post(
        f"/api/worker-app/chat/threads/{thread_id}/messages",
        headers=worker_headers,
        json={"body": "plaintext-ok-before-keys"},
    )
    assert allowed.status_code == 200


def test_chat_rejects_plaintext_when_both_keys_registered(client_and_db, monkeypatch):
    from backend.app.platform.security import e2e_policy

    monkeypatch.setattr(e2e_policy, "e2e_chat_required", lambda: True)
    client, db_path = client_and_db
    from backend.tests.test_e2e_identity_routes import (
        _create_company,
        _superadmin_headers,
        _worker_session_headers,
    )

    admin_headers = _superadmin_headers(client)
    company_id = _create_company(client, admin_headers, "E2EPolicyCo2")
    worker_headers, worker_id = _worker_session_headers(client, db_path, company_id)
    pub = _fake_spki_b64()

    admin_put = client.put(
        "/api/e2e/identity/admin/me",
        headers=admin_headers,
        json={"publicKeySpkiB64": pub, "company_id": company_id},
    )
    assert admin_put.status_code == 200

    worker_put = client.put(
        "/api/e2e/identity/me",
        headers=worker_headers,
        json={"publicKeySpkiB64": pub},
    )
    assert worker_put.status_code == 200

    thread = client.post(
        "/api/worker-app/chat/threads",
        headers=worker_headers,
        json={"subject": "general"},
    )
    assert thread.status_code == 200
    thread_id = thread.get_json().get("threadId") or ""
    assert thread_id

    blocked = client.post(
        f"/api/worker-app/chat/threads/{thread_id}/messages",
        headers=worker_headers,
        json={"body": "plaintext-not-allowed"},
    )
    assert blocked.status_code == 400
    assert blocked.get_json().get("error") == "e2e_required"

    allowed = client.post(
        f"/api/worker-app/chat/threads/{thread_id}/messages",
        headers=worker_headers,
        json={"body": _fake_envelope()},
    )
    assert allowed.status_code == 200
