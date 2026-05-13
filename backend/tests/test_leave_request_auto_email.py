from __future__ import annotations

import base64
import sqlite3
from contextlib import closing
from pathlib import Path
import sys

import pytest


# Make backend/server.py importable when pytest is run from repo root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import server


@pytest.fixture()
def client_and_db(tmp_path, monkeypatch):
    db_path = tmp_path / "baupass-test.db"
    monkeypatch.setattr(server, "DB_PATH", db_path)
    server.request_rate_state.clear()
    server.failed_login_attempts.clear()
    server.init_db()
    server.app.config.update(TESTING=True)

    with server.app.test_client() as client:
        yield client, db_path


def _superadmin_headers(client):
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


def _create_worker(client, headers):
    create_response = client.post(
        "/api/workers",
        json={
            "companyId": "cmp-default",
            "firstName": "Max",
            "lastName": "Mustermann",
            "insuranceNumber": "A123456789",
            "workerType": "worker",
            "role": "Monteur",
            "site": "Nordtor",
            "validUntil": "2028-12-31",
            "status": "aktiv",
            "photoData": "data:image/png;base64,AAA",
            "badgePin": "1234",
            "physicalCardId": "NFC-LEAVE-001",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    return create_response.get_json()["id"]


def _worker_session_headers(client, admin_headers, worker_id):
    access_response = client.post(f"/api/workers/{worker_id}/app-access", headers=admin_headers)
    assert access_response.status_code == 200
    access_token = access_response.get_json()["accessToken"]

    login_response = client.post("/api/worker-app/login", json={"accessToken": access_token})
    assert login_response.status_code == 200
    worker_token = login_response.get_json()["token"]
    return {"Authorization": f"Bearer {worker_token}"}


def test_submit_leave_request_auto_sends_pdf_to_manager(client_and_db, monkeypatch):
    client, db_path = client_and_db
    admin_headers = _superadmin_headers(client)
    worker_id = _create_worker(client, admin_headers)
    worker_headers = _worker_session_headers(client, admin_headers, worker_id)

    captured = {"calls": []}

    def _fake_send(subject, from_email, from_name, to_email, text_body, html_body, attachments=None):
        captured["calls"].append(
            {
                "subject": subject,
                "to_email": to_email,
                "attachments": attachments or [],
            }
        )
        return True, "", "mock"

    monkeypatch.setattr(server, "_send_via_any_api", _fake_send)
    monkeypatch.setattr(server, "_build_leave_request_pdf_bytes", lambda _payload: b"%PDF-1.4\n%test\n")

    response = client.post(
        "/api/worker-app/leave-requests",
        json={
            "type": "urlaub",
            "start_date": "2026-06-01",
            "end_date": "2026-06-03",
            "note": "Bitte freigeben",
            "recipient_email": "chef@example.com",
        },
        headers=worker_headers,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["mail_sent"] is True
    assert payload["mail_recipients"] == ["chef@example.com"]
    assert payload["mail_failed"] == []

    assert len(captured["calls"]) == 1
    first_call = captured["calls"][0]
    assert first_call["to_email"] == "chef@example.com"
    assert "Neuer Antrag" in first_call["subject"]

    attachments = first_call["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["filename"].startswith("urlaubsantrag-")
    assert attachments[0]["mime_type"] == "application/pdf"
    decoded = base64.b64decode(attachments[0]["content_b64"])
    assert decoded.startswith(b"%PDF-")

    with closing(sqlite3.connect(db_path)) as db:
        row = db.execute(
            "SELECT email_forwarded_to FROM leave_requests WHERE worker_id = ? ORDER BY created_at DESC LIMIT 1",
            (worker_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "chef@example.com"
