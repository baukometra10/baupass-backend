"""Leave request approve/reject API."""
from __future__ import annotations

from backend import server


def _superadmin_headers(client):
    response = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['token']}"}


def _create_worker(client, headers):
    response = client.post(
        "/api/workers",
        json={
            "companyId": "cmp-default",
            "firstName": "Leave",
            "lastName": "Tester",
            "insuranceNumber": "A987654321",
            "workerType": "worker",
            "role": "Monteur",
            "site": "Nordtor",
            "validUntil": "2028-12-31",
            "status": "aktiv",
            "photoData": "data:image/png;base64,AAA",
            "badgePin": "1234",
            "complianceSignatureData": "data:image/png;base64,AAA",
            "physicalCardId": "NFC-LEAVE-REVIEW-001",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def _worker_session_headers(client, admin_headers, worker_id):
    access_response = client.post(f"/api/workers/{worker_id}/app-access", headers=admin_headers)
    assert access_response.status_code == 200
    access_token = access_response.get_json()["accessToken"]
    login_response = client.post("/api/worker-app/login", json={"accessToken": access_token})
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.get_json()['token']}"}


def _submit_leave(client, worker_headers):
    response = client.post(
        "/api/worker-app/leave-requests",
        json={
            "type": "urlaub",
            "start_date": "2026-07-01",
            "end_date": "2026-07-05",
            "note": "Familienurlaub",
        },
        headers=worker_headers,
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def test_reject_leave_returns_ok_when_push_succeeds(client_and_db, monkeypatch):
    client, _ = client_and_db
    admin_headers = _superadmin_headers(client)
    worker_id = _create_worker(client, admin_headers)
    worker_headers = _worker_session_headers(client, admin_headers, worker_id)
    leave_id = _submit_leave(client, worker_headers)

    monkeypatch.setattr(
        "backend.app.platform.push.automation.push_leave_decision",
        lambda db, row, new_status, review_note="": {"pushSent": 1, "delivered": True},
    )

    reject = client.put(
        f"/api/leave-requests/{leave_id}",
        json={"status": "abgelehnt", "review_note": "Zu wenig Personal in dieser Woche"},
        headers=admin_headers,
    )
    assert reject.status_code == 200
    payload = reject.get_json()
    assert payload.get("ok") is True

    row = client.get("/api/leave-requests", headers=admin_headers).get_json()
    match = next(item for item in row if item["id"] == leave_id)
    assert match["status"] == "abgelehnt"
    assert match["review_note"] == "Zu wenig Personal in dieser Woche"


def test_reject_leave_post_method(client_and_db, monkeypatch):
    client, _ = client_and_db
    admin_headers = _superadmin_headers(client)
    worker_id = _create_worker(client, admin_headers)
    worker_headers = _worker_session_headers(client, admin_headers, worker_id)
    leave_id = _submit_leave(client, worker_headers)

    monkeypatch.setattr(
        "backend.app.platform.push.automation.push_leave_decision",
        lambda db, row, new_status, review_note="": {"pushSent": 1, "delivered": True},
    )

    reject = client.post(
        f"/api/leave-requests/{leave_id}",
        json={"status": "abgelehnt", "review_note": "Per POST"},
        headers=admin_headers,
    )
    assert reject.status_code == 200
    assert reject.get_json().get("ok") is True
