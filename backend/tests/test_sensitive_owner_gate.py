"""Owner-Freigabe + Pförtner (turnstile) hard-deny for docs/contracts/exports."""
from __future__ import annotations


def _superadmin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def _create_company_with_gate(client, headers, name: str) -> tuple[str, dict]:
    response = client.post(
        "/api/companies",
        json={
            "name": name,
            "contact": "x",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 1,
            "plan": "professional",
        },
        headers=headers,
    )
    assert response.status_code in (200, 201), response.get_json()
    payload = response.get_json() or {}
    company = payload.get("company") or {}
    cid = str(company.get("id") or payload.get("id") or "")
    gate = payload.get("turnstileCredentials") or {}
    admin = payload.get("adminCredentials") or {}
    return cid, {"gate": gate, "admin": admin}


def _login(client, username: str, password: str = "1234", *, scope: str = "company-admin"):
    resp = client.post(
        "/api/login",
        json={"username": username, "password": password, "loginScope": scope},
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json() or {}
    token = body.get("token")
    assert token, body
    return {"Authorization": f"Bearer {token}"}


def _setup_owner_lock(client, headers, company_id: str, monkeypatch):
    monkeypatch.setenv("BAUPASS_ENV", "testing")
    monkeypatch.setattr(
        "backend.app.platform.security.contracts_lock._OTP_REQUEST_MIN_SECONDS",
        0,
    )
    monkeypatch.setattr(
        "backend.app.platform.security.contracts_lock._OTP_REQUEST_MAX_PER_HOUR",
        100,
    )
    req = client.post(
        "/api/contracts/lock/request-otp",
        json={
            "company_id": company_id,
            "setup": True,
            "phone": "+491701234567",
            "email": "owner@example.com",
        },
        headers=headers,
    )
    assert req.status_code == 200, req.get_json()
    code = (req.get_json() or {}).get("debugCode")
    assert code
    verify = client.post(
        "/api/contracts/lock/verify",
        json={
            "company_id": company_id,
            "setup": True,
            "phone": "+491701234567",
            "email": "owner@example.com",
            "code": code,
        },
        headers=headers,
    )
    assert verify.status_code == 200, verify.get_json()
    locked = client.post(
        "/api/contracts/lock",
        json={"company_id": company_id},
        headers=headers,
    )
    assert locked.status_code == 200


def _unlock_again(client, headers, company_id: str):
    req = client.post(
        "/api/contracts/lock/request-otp",
        json={"company_id": company_id},
        headers=headers,
    )
    assert req.status_code == 200, req.get_json()
    code = (req.get_json() or {}).get("debugCode")
    assert code
    verify = client.post(
        "/api/contracts/lock/verify",
        json={"company_id": company_id, "code": code},
        headers=headers,
    )
    assert verify.status_code == 200, verify.get_json()


def test_turnstile_docs_editor_allowed_contracts_still_denied(client_and_db, monkeypatch):
    """Pförtner may use the free docs editor; Arbeitsverträge stay blocked."""
    client, _ = client_and_db
    sa = _superadmin_headers(client)
    cid, creds = _create_company_with_gate(client, sa, "GateDocsDenyCo")
    gate = creds["gate"]
    turnstile_headers = _login(client, gate["username"], gate["password"], scope="turnstile")

    called = {"n": 0}

    def fake_notify(*_a, **_k):
        called["n"] += 1
        return {"audit": True, "alert": True, "email": False, "sms": False}

    monkeypatch.setattr(
        "backend.app.platform.security.contracts_lock.notify_owner_sensitive_attempt",
        fake_notify,
    )

    listed = client.get(f"/api/v2/docs?company_id={cid}", headers=turnstile_headers)
    assert listed.status_code == 200, listed.get_json()

    created = client.post(
        f"/api/v2/docs?company_id={cid}",
        headers=turnstile_headers,
        json={
            "company_id": cid,
            "title": "Pforte Notiz",
            "mode": "general",
            "contentHtml": "<p>Reparatur</p>",
        },
    )
    assert created.status_code == 201, created.get_json()

    blocked = client.post(
        f"/api/v2/docs/from-contract?company_id={cid}",
        headers=turnstile_headers,
        json={"company_id": cid, "contractId": "ctr-turnstile-block", "text": "AV"},
    )
    assert blocked.status_code == 403
    body = blocked.get_json() or {}
    assert body.get("error") in {"sensitive_forbidden", "forbidden", "contracts_locked", "owner_setup_required"}
    assert called["n"] >= 1


def test_turnstile_contracts_list_denied_and_notifies(client_and_db, monkeypatch):
    client, _ = client_and_db
    sa = _superadmin_headers(client)
    cid, creds = _create_company_with_gate(client, sa, "GateContractsDenyCo")
    gate = creds["gate"]
    turnstile_headers = _login(client, gate["username"], gate["password"], scope="turnstile")

    called = {"n": 0}

    def fake_notify(*_a, **_k):
        called["n"] += 1
        return {"audit": True}

    monkeypatch.setattr(
        "backend.app.platform.security.contracts_lock.notify_owner_sensitive_attempt",
        fake_notify,
    )

    resp = client.get(f"/api/contracts?company_id={cid}", headers=turnstile_headers)
    assert resp.status_code == 403
    body = resp.get_json() or {}
    assert body.get("error") == "sensitive_forbidden"
    assert called["n"] >= 1


def test_general_docs_share_free_without_unlock(client_and_db, monkeypatch):
    """Ordinary docs editor stays usable without owner OTP; contracts stay gated elsewhere."""
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    cid, _creds = _create_company_with_gate(client, headers, "DocsShareLockCo")

    created = client.post(
        f"/api/v2/docs?company_id={cid}",
        headers=headers,
        json={
            "company_id": cid,
            "title": "ShareMe",
            "mode": "general",
            "contentHtml": "<p>Site note</p>",
        },
    )
    assert created.status_code == 201, created.get_json()
    doc_id = created.get_json()["document"]["id"]

    _setup_owner_lock(client, headers, cid, monkeypatch)

    # General docs remain free even when contracts lock is active.
    ok = client.post(
        f"/api/v2/docs/{doc_id}/share?company_id={cid}",
        headers=headers,
        json={"company_id": cid, "ttlHours": 72},
    )
    assert ok.status_code == 200, ok.get_json()
    assert ok.get_json().get("token")


def test_contract_docs_still_require_unlock(client_and_db, monkeypatch):
    """OTP contracts lock is retired — company-admin may share contract docs without unlock.

    Turnstile/office remain blocked via role checks (covered elsewhere).
    """
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    cid, _creds = _create_company_with_gate(client, headers, "DocsContractLockCo")

    created = client.post(
        f"/api/v2/docs?company_id={cid}",
        headers=headers,
        json={
            "company_id": cid,
            "title": "AV",
            "mode": "contract",
            "contractId": "ctr-lock-1",
            "contentHtml": "<p>Vertrag</p>",
        },
    )
    assert created.status_code == 201, created.get_json()
    doc_id = created.get_json()["document"]["id"]

    # Legacy lock APIs may still succeed for setup, but must not gate admin share.
    _setup_owner_lock(client, headers, cid, monkeypatch)

    shared = client.post(
        f"/api/v2/docs/{doc_id}/share?company_id={cid}",
        headers=headers,
        json={"company_id": cid, "ttlHours": 72},
    )
    assert shared.status_code == 200, shared.get_json()
    assert shared.get_json().get("token")


def test_ai_operator_blocks_turnstile_docs_contracts(client_and_db, monkeypatch):
    client, db_path = client_and_db
    sa = _superadmin_headers(client)
    cid, _creds = _create_company_with_gate(client, sa, "AiGateBlockCo")

    called = {"n": 0}

    def fake_notify(*_a, **_k):
        called["n"] += 1
        return {"audit": True}

    monkeypatch.setattr(
        "backend.app.platform.security.contracts_lock.notify_owner_sensitive_attempt",
        fake_notify,
    )

    from backend.app.platform.ai.operator_tasks import try_operator_task
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        hit = try_operator_task(
            db,
            cid,
            "Öffne Verträge",
            role="turnstile",
            lang="de",
        )
    assert hit is not None
    assert hit.get("blocked") is True
    assert "gesperrt" in (hit.get("answer") or "").lower() or hit.get("ownerNotified")
    assert called["n"] >= 1
