from __future__ import annotations

import io
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
    worker_id = "wrk-chat-1"
    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number, role, site, valid_until,
                status, photo_data, badge_id, badge_id_lookup, badge_pin_hash, worker_type
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', 'worker')
            """,
            (
                worker_id,
                company_id,
                "Chat",
                "Worker",
                "12 345678 A 555",
                "Maler",
                "Testsite",
                "2026-12-31",
                "aktiv",
                "",
                "CHT-100",
                "CHT100",
            ),
        )
        db.commit()
    return worker_id


def test_contract_templates_and_draft(client_and_db):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "ContractCo")

    templates = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    assert templates.status_code == 200
    template_rows = templates.get_json().get("templates") or []
    assert len(template_rows) >= 3

    draft = client.post(
        "/api/contracts/draft",
        json={
            "company_id": company_id,
            "template_id": template_rows[0]["id"],
            "title": "Arbeitsvertrag Test",
            "language": "de",
            "notes": "Start 01.07.2026, Vollzeit, 30 Urlaubstage.",
        },
        headers=headers,
    )
    assert draft.status_code == 200
    payload = draft.get_json()
    assert payload["contract"]["id"]
    assert payload["contract"]["draft_text"]

    contract_id = payload["contract"]["id"]
    deleted = client.delete(f"/api/contracts/{contract_id}?company_id={company_id}", headers=headers)
    assert deleted.status_code == 200
    missing = client.get(f"/api/contracts/{contract_id}?company_id={company_id}", headers=headers)
    assert missing.status_code == 404


def test_contracts_require_professional_plan(client_and_db):
    client, db_path = client_and_db
    headers = _superadmin_headers(client)
    response = client.post(
        "/api/companies",
        json={
            "name": "ContractPlanCo",
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
    company_id = str(company.get("id") or payload.get("id") or "")
    admin_username = (payload.get("adminCredentials") or {}).get("username") or ""
    assert company_id and admin_username
    with closing(sqlite3.connect(db_path)) as db:
        db.execute("UPDATE companies SET plan = ? WHERE id = ?", ("tageskarte", company_id))
        db.commit()
    login = client.post(
        "/api/login",
        json={"username": admin_username, "password": "1234", "loginScope": "company-admin"},
    )
    assert login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {login.get_json()['token']}"}
    blocked = client.get("/api/contracts/templates", headers=admin_headers)
    assert blocked.status_code == 403
    assert blocked.get_json().get("error") == "feature_not_available"


def test_chat_thread_message_and_attachment(client_and_db):
    client, db_path = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "ChatCo")
    worker_id = _create_worker_direct(db_path, company_id)

    create = client.post(
        "/api/worker-app/chat/threads",
        json={"subject": "general"},
        headers={"Authorization": "Bearer invalid"},
    )
    assert create.status_code == 401

    # Admin-side thread bootstrapping via service endpoint expectations
    from backend.app.domains.chat.service import ChatService
    from backend.server import get_db

    with client.application.app_context():
        service = ChatService(get_db())
        thread_id = service.get_or_create_worker_thread(company_id=company_id, worker_id=worker_id, subject="general")

    send = client.post(
        f"/api/chat/threads/{thread_id}/messages?company_id={company_id}",
        json={"worker_id": worker_id, "body": "Hallo vom Unternehmen"},
        headers=headers,
    )
    assert send.status_code == 200
    message_id = send.get_json()["message"]["id"]

    attach = client.post(
        f"/api/chat/threads/{thread_id}/attachments?company_id={company_id}",
        data={
            "message_id": message_id,
            "worker_id": worker_id,
            "file": (io.BytesIO(b"hello"), "chat.txt"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert attach.status_code == 200
    assert attach.get_json()["attachment"]["id"]
