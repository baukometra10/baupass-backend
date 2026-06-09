import sqlite3
from contextlib import closing
from pathlib import Path
import sys

import pytest

from backend import server  # noqa: E402


def _auth_headers(client):
    response = client.post(
        "/api/login",
        json={
            "username": "superadmin",
            "password": "1234",
            "loginScope": "server-admin",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    return {"Authorization": f"Bearer {payload['token']}"}


def _worker_payload(company_id, physical_card_id, **overrides):
    payload = {
        "companyId": company_id,
        "firstName": "Max",
        "lastName": "Muster",
        "insuranceNumber": "A123456789",
        "workerType": "worker",
        "role": "Monteur",
        "site": "Nordtor",
        "validUntil": "2028-12-31",
        "status": "aktiv",
        "photoData": "data:image/png;base64,AAA",
        "badgePin": "1234",
        "complianceSignatureData": "data:image/png;base64,AAA",
        "physicalCardId": physical_card_id,
    }
    payload.update(overrides)
    return payload


def _issue_turnstile_api_key(db_path, user_id="usr-turnstile"):
    api_key = server.create_turnstile_api_key()
    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            "UPDATE users SET api_key_hash = ? WHERE id = ?",
            (server.hash_turnstile_api_key(api_key), user_id),
        )
        db.commit()
    return api_key


def _create_company_with_gate(client, headers, name="Firma Unified"):
    response = client.post(
        "/api/companies",
        json={
            "name": name,
            "contact": "Unified Contact",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 1,
        },
        headers=headers,
    )
    assert response.status_code == 201
    payload = response.get_json()
    return payload["company"]["id"], payload["turnstileCredentials"]["apiKey"]


def _create_worker(client, headers, company_id="cmp-default", physical_card_id="CARD-UNI-1"):
    response = client.post(
        "/api/workers",
        json=_worker_payload(company_id, physical_card_id),
        headers=headers,
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def _issue_identity_token(client, headers, worker_id):
    response = client.post(
        f"/api/workers/{worker_id}/identity-token",
        json={"rotate": False},
        headers=headers,
    )
    assert response.status_code == 200
    token = response.get_json().get("token")
    assert token and token.startswith("wid_")
    return token


def test_unified_scan_success_and_duplicate_ignored(client_and_db):
    client, _ = client_and_db
    admin_headers = _auth_headers(client)
    company_id, gate_key = _create_company_with_gate(client, admin_headers, name="Firma Unified A")
    worker_id = _create_worker(client, admin_headers, company_id=company_id)
    token = _issue_identity_token(client, admin_headers, worker_id)

    gate_headers = {"X-Gate-Key": gate_key}
    scan_payload = {
        "token": token,
        "device_id": "gate-device-1",
        "source": "qr",
        "direction": "check-in",
        "gate": "Unified Gate 1",
    }

    first_response = client.post("/api/scan", json=scan_payload, headers=gate_headers)
    assert first_response.status_code == 201, first_response.get_json()
    first_json = first_response.get_json()
    assert first_json.get("ok") is True
    assert first_json.get("tokenAccepted") is True
    assert first_json.get("direction") == "check-in"

    second_response = client.post("/api/scan", json=scan_payload, headers=gate_headers)
    assert second_response.status_code == 202
    second_json = second_response.get_json()
    assert second_json.get("ok") is True
    assert bool(second_json.get("duplicateIgnored") or second_json.get("duplicateReplay")) is True


def test_unified_scan_rejects_revoked_token_and_allows_reactivated_token(client_and_db):
    client, _ = client_and_db
    admin_headers = _auth_headers(client)
    company_id, gate_key = _create_company_with_gate(client, admin_headers, name="Firma Unified B")
    worker_id = _create_worker(client, admin_headers, company_id=company_id, physical_card_id="CARD-UNI-2")
    token = _issue_identity_token(client, admin_headers, worker_id)

    revoke_response = client.post(
        f"/api/workers/{worker_id}/identity-token/status",
        json={"status": "revoked"},
        headers=admin_headers,
    )
    assert revoke_response.status_code == 200
    assert revoke_response.get_json().get("status") == "revoked"

    gate_headers = {"X-Gate-Key": gate_key}
    revoked_scan_response = client.post(
        "/api/scan",
        json={
            "token": token,
            "device_id": "gate-device-2",
            "source": "qr",
            "direction": "check-in",
            "gate": "Unified Gate 2",
        },
        headers=gate_headers,
    )
    assert revoked_scan_response.status_code == 401
    assert revoked_scan_response.get_json().get("error") == "token_revoked"

    activate_response = client.post(
        f"/api/workers/{worker_id}/identity-token/status",
        json={"status": "active"},
        headers=admin_headers,
    )
    assert activate_response.status_code == 200
    assert activate_response.get_json().get("status") == "active"

    active_scan_response = client.post(
        "/api/scan",
        json={
            "token": token,
            "device_id": "gate-device-2",
            "source": "qr",
            "direction": "check-in",
            "gate": "Unified Gate 2",
        },
        headers=gate_headers,
    )
    assert active_scan_response.status_code == 201, active_scan_response.get_json()
    assert active_scan_response.get_json().get("ok") is True


def test_unified_scan_validates_required_fields(client_and_db):
    client, _ = client_and_db
    admin_headers = _auth_headers(client)
    company_id, gate_key = _create_company_with_gate(client, admin_headers, name="Firma Unified C")
    worker_id = _create_worker(client, admin_headers, company_id=company_id, physical_card_id="CARD-UNI-3")
    token = _issue_identity_token(client, admin_headers, worker_id)

    gate_headers = {"X-Gate-Key": gate_key}

    missing_device_response = client.post(
        "/api/scan",
        json={"token": token, "source": "qr"},
        headers=gate_headers,
    )
    assert missing_device_response.status_code == 400
    assert missing_device_response.get_json().get("error") == "missing_device_id"

    invalid_token_response = client.post(
        "/api/scan",
        json={
            "token": "wid_invalid_token",
            "device_id": "gate-device-3",
            "source": "qr",
        },
        headers=gate_headers,
    )
    assert invalid_token_response.status_code == 401
    assert invalid_token_response.get_json().get("error") == "invalid_token"
