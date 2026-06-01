"""Smoke tests: enterprise catalog, geofence, automation."""
from __future__ import annotations

import pytest

from backend import server  # noqa: E402


def _superadmin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def _company_id_from_create(response) -> str:
    payload = response.get_json() or {}
    company = payload.get("company") or {}
    return str(company.get("id") or payload.get("id") or "")


def test_enterprise_catalog_preview(client_and_db):
    client, _ = client_and_db
    r = client.get("/api/platform/enterprise-catalog/preview")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("layerCount") >= 16
    assert data.get("preview") is True


def test_enterprise_catalog_includes_billing_flags(client_and_db):
    client, _ = client_and_db
    h = _superadmin_headers(client)
    r = client.get("/api/platform/enterprise-catalog", headers=h)
    assert r.status_code == 200
    billing = r.get_json().get("billing") or {}
    assert "stripeConfigured" in billing
    assert billing.get("selfServeCheckout") is False


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
    cid = _company_id_from_create(r)
    assert cid
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
    client, db_path = client_and_db
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(db_path)) as db:
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    if "automation_rules" not in tables:
        pytest.skip("automation_rules not in test init_db schema yet")

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
    cid = _company_id_from_create(r)
    assert cid
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
