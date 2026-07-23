"""Contracts owner lock via SMS/email OTP."""
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


def test_contracts_open_without_owner_phone(client_and_db):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "OpenContractsCo")
    status = client.get(f"/api/contracts/lock-status?company_id={company_id}", headers=headers)
    assert status.status_code == 200
    body = status.get_json()
    assert body["lockRequired"] is False
    assert body["unlocked"] is True
    templates = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    assert templates.status_code == 200


def test_contracts_lock_otp_flow(client_and_db, monkeypatch):
    client, _db_path = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "LockedContractsCo")

    monkeypatch.setenv("BAUPASS_ENV", "testing")

    req = client.post(
        "/api/contracts/lock/request-otp",
        json={"company_id": company_id, "setup": True, "phone": "+491701234567", "email": "owner@example.com"},
        headers=headers,
    )
    assert req.status_code == 200, req.get_json()
    code = (req.get_json() or {}).get("debugCode")
    assert code

    # Still open until phone is verified/saved
    open_before = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    assert open_before.status_code == 200

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
    assert verify.get_json().get("unlocked") is True

    # Relock
    locked = client.post(
        "/api/contracts/lock",
        json={"company_id": company_id},
        headers=headers,
    )
    assert locked.status_code == 200

    blocked = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    assert blocked.status_code == 403
    assert blocked.get_json().get("error") == "contracts_locked"

    # Request + verify again
    req2 = client.post(
        "/api/contracts/lock/request-otp",
        json={"company_id": company_id},
        headers=headers,
    )
    assert req2.status_code == 200
    code2 = (req2.get_json() or {}).get("debugCode")
    assert code2
    verify2 = client.post(
        "/api/contracts/lock/verify",
        json={"company_id": company_id, "code": code2},
        headers=headers,
    )
    assert verify2.status_code == 200
    ok_again = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    assert ok_again.status_code == 200
