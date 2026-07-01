"""Worker QR join preview and qrLaunch badge login (pytest)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

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


def _seed_worker_with_pin(client, *, badge_id="BP-QR-FLOW", pin="1234"):
    headers = _auth_headers(client)
    create_response = client.post(
        "/api/workers",
        json={
            "companyId": "cmp-default",
            "firstName": "QR",
            "lastName": "Tester",
            "insuranceNumber": f"INS-{uuid.uuid4().hex[:8].upper()}",
            "workerType": "worker",
            "role": "Monteur",
            "site": "Nordtor",
            "validUntil": "2099-12-31",
            "status": "aktiv",
            "photoData": "data:image/png;base64,AAA",
            "badgePin": pin,
            "complianceSignatureData": "data:image/png;base64,AAA",
            "physicalCardId": badge_id,
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    body = create_response.get_json()
    worker_id = body["id"]
    resolved_badge = body.get("badgeId") or body.get("badge_id") or badge_id
    return worker_id, headers, resolved_badge


@pytest.fixture()
def client(client_and_db):
    return client_and_db[0]


def test_app_access_link_includes_badge_and_fast_flag(client):
    worker_id, headers, badge_id = _seed_worker_with_pin(client)
    access_response = client.post(f"/api/workers/{worker_id}/app-access", headers=headers)
    assert access_response.status_code == 200
    body = access_response.get_json()
    assert body.get("badgeId") == badge_id
    link = body.get("link") or ""
    assert f"badge={badge_id}" in link
    assert "fast=1" in link
    assert "access=" in link
    assert "/emp-app.html" in link


def test_join_preview_get_returns_badge_without_consuming_token(client):
    worker_id, headers, badge_id = _seed_worker_with_pin(client)
    access_response = client.post(f"/api/workers/{worker_id}/app-access", headers=headers)
    access_token = access_response.get_json()["accessToken"]

    preview_response = client.get(f"/api/worker-app/join-preview?access={access_token}")
    assert preview_response.status_code == 200
    preview = preview_response.get_json()
    assert preview.get("badgeId") == badge_id
    assert preview.get("tokenValid") is True
    assert preview.get("tokenUsed") is False
    assert isinstance(preview.get("company"), dict)
    assert preview["company"].get("name")

    login_response = client.post("/api/worker-app/login", json={"accessToken": access_token})
    assert login_response.status_code == 200
    login_payload = login_response.get_json()
    assert isinstance(login_payload.get("company"), dict)
    assert login_payload["company"].get("portalDisplayName") or login_payload["company"].get("name")

    preview_after = client.get(f"/api/worker-app/join-preview?access={access_token}")
    assert preview_after.status_code == 200
    preview_used = preview_after.get_json()
    assert preview_used.get("badgeId") == badge_id
    assert preview_used.get("tokenUsed") is True


def test_qr_launch_badge_login_skips_geofence(client):
    worker_id, headers, badge_id = _seed_worker_with_pin(client, pin="5678")
    login_response = client.post(
        "/api/worker-app/login",
        json={
            "badgeId": badge_id,
            "badgePin": "5678",
            "qrLaunch": True,
        },
    )
    assert login_response.status_code == 200
    assert login_response.get_json().get("token")


def test_badge_login_without_qr_launch_requires_location_when_geofenced(client):
    with server.app.app_context():
        db = server.get_db()
        db.execute(
            """
            INSERT OR IGNORE INTO companies (id, name, contact, plan, status, access_mode)
            VALUES ('cmp-qr-geo', 'QR Geo Co', '', 'professional', 'active', 'gate')
            """
        )
        db.execute("DELETE FROM geofences WHERE company_id = 'cmp-qr-geo'")
        db.execute(
            """
            INSERT INTO geofences (id, company_id, site_name, latitude, longitude, radius_meters, active, created_at)
            VALUES ('gf-qr-geo', 'cmp-qr-geo', 'Hauptbaustelle', 52.52, 13.405, 80, 1, '2099-01-01T00:00:00Z')
            """
        )
        worker_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, status, photo_data,
                badge_id, badge_id_lookup, badge_pin_hash, physical_card_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                worker_id,
                "cmp-qr-geo",
                "Geo",
                "Worker",
                "INS-GEO",
                "worker",
                "arbeiter",
                "Hauptbaustelle",
                "2099-12-31",
                "aktiv",
                "",
                "BP-QR-GEO",
                "BP-QR-GEO",
                server.generate_password_hash("9999"),
                None,
            ),
        )
        db.commit()

    login_response = client.post(
        "/api/worker-app/login",
        json={
            "badgeId": "BP-QR-GEO",
            "badgePin": "9999",
        },
    )
    assert login_response.status_code == 400
    assert login_response.get_json().get("error") == "worker_geolocation_required"
