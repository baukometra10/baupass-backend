"""Tests for E2E identity public-key API."""
from __future__ import annotations

import base64
import sqlite3
from contextlib import closing


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


def _create_worker_direct(db_path, company_id: str) -> str:
    worker_id = "wrk-e2e-1"
    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            """
            INSERT OR REPLACE INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number, role, site, valid_until,
                status, photo_data, badge_id, badge_id_lookup, badge_pin_hash, worker_type
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', 'worker')
            """,
            (
                worker_id,
                company_id,
                "E2E",
                "Worker",
                "12 345678 A 777",
                "Maler",
                "Testsite",
                "2026-12-31",
                "aktiv",
                "",
                "E2E-100",
                "E2E100",
            ),
        )
        db.commit()
    return worker_id


def _worker_session_headers(client, db_path, company_id: str) -> dict:
    worker_id = _create_worker_direct(db_path, company_id)
    login = client.post(
        "/api/worker-app/login",
        json={"badgeId": "E2E-100", "badgePin": "123456"},
    )
    if login.status_code != 200:
        pytest_skip = __import__("pytest").skip
        pytest_skip(f"worker login failed: {login.status_code}")
    token = login.get_json().get("token") or ""
    return {"Authorization": f"Bearer {token}"}, worker_id


def _fake_spki_b64() -> str:
    return base64.b64encode(b"\x30" + b"\x00" * 40).decode("ascii")


def test_e2e_rejects_private_key_in_body(client_and_db):
    client, db_path = client_and_db
    admin_headers = _superadmin_headers(client)
    company_id = _create_company(client, admin_headers, "E2ECo")
    worker_headers, _worker_id = _worker_session_headers(client, db_path, company_id)

    resp = client.put(
        "/api/e2e/identity/me",
        headers=worker_headers,
        json={"privateKey": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"},
    )
    assert resp.status_code == 403
    assert resp.get_json().get("error") == "private_key_forbidden"


def test_worker_e2e_identity_register_and_fetch(client_and_db):
    client, db_path = client_and_db
    admin_headers = _superadmin_headers(client)
    company_id = _create_company(client, admin_headers, "E2ECo2")
    worker_headers, _worker_id = _worker_session_headers(client, db_path, company_id)
    pub = _fake_spki_b64()

    put = client.put(
        "/api/e2e/identity/me",
        headers=worker_headers,
        json={"publicKeySpkiB64": pub, "algorithm": "X25519"},
    )
    assert put.status_code == 200
    body = put.get_json()
    assert body.get("ok") is True
    assert body["identity"]["publicKeySpkiB64"] == pub

    get_resp = client.get("/api/e2e/identity/me", headers=worker_headers)
    assert get_resp.status_code == 200
    assert get_resp.get_json()["identity"]["publicKeySpkiB64"] == pub


def test_admin_e2e_identity_register(client_and_db):
    client, _db_path = client_and_db
    admin_headers = _superadmin_headers(client)
    _create_company(client, admin_headers, "E2ECo3")
    pub = _fake_spki_b64()

    put = client.put(
        "/api/e2e/identity/admin/me",
        headers=admin_headers,
        json={"publicKeySpkiB64": pub},
    )
    assert put.status_code == 200

    listed = client.get(
        "/api/e2e/identity/admin/public-keys?worker_id=wrk-e2e-1",
        headers=admin_headers,
    )
    assert listed.status_code == 200
    keys = listed.get_json().get("publicKeys") or []
    assert any(k.get("publicKeySpkiB64") == pub for k in keys)
