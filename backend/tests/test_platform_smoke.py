"""Smoke tests: enterprise catalog, geofence, automation."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import server  # noqa: E402


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
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def test_enterprise_catalog_preview(client_and_db):
    client, _ = client_and_db
    r = client.get("/api/platform/enterprise-catalog/preview")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("layerCount") >= 16
    assert data.get("preview") is True


def test_setup_status_public(client_and_db):
    client, _ = client_and_db
    r = client.get("/api/platform/setup-status")
    assert r.status_code == 200
    assert "redis" in r.get_json()


def test_geofence_crud(client_and_db):
    client, _ = client_and_db
    h = _superadmin_headers(client)
    r = client.post(
        "/api/companies",
        json={
            "name": "GeoTestCo",
            "contact": "x",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 0,
        },
        headers=h,
    )
    assert r.status_code in (200, 201)
    cid = r.get_json().get("id")
    r2 = client.post(
        f"/api/geofences/admin?company_id={cid}",
        json={
            "site_name": "Baustelle A",
            "latitude": 52.52,
            "longitude": 13.405,
            "radius_meters": 80,
        },
        headers=h,
    )
    assert r2.status_code == 201
    r3 = client.get(f"/api/geofences/admin?company_id={cid}", headers=h)
    assert r3.status_code == 200
    assert len(r3.get_json().get("geofences", [])) >= 1


def test_automation_rule_create(client_and_db):
    client, _ = client_and_db
    h = _superadmin_headers(client)
    r = client.post(
        "/api/companies",
        json={
            "name": "AutoCo",
            "contact": "x",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 0,
        },
        headers=h,
    )
    cid = r.get_json().get("id")
    r2 = client.post(
        f"/api/automation/rules?company_id={cid}",
        json={
            "name": "Check-in notify",
            "trigger_event": "worker.checkin",
            "conditions": [],
            "actions": [{"type": "log"}],
            "enabled": True,
        },
        headers=h,
    )
    assert r2.status_code == 201
    r3 = client.get(f"/api/automation/rules?company_id={cid}", headers=h)
    assert len(r3.get_json().get("rules", [])) >= 1
