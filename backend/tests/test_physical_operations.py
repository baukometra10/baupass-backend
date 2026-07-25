"""Physical Operations OS endpoints (smoke)."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

from backend import server  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "baupass-test.db"
    monkeypatch.setattr(server, "DB_PATH", db_path)
    server.request_rate_state.clear()
    server.failed_login_attempts.clear()
    server.init_db()
    server.app.config.update(TESTING=True)
    with server.app.test_client() as test_client:
        yield test_client


def test_ops_os_overview_requires_auth(client):
    r = client.get("/api/ops-os/overview")
    assert r.status_code in (401, 403)


def test_ops_os_summary_requires_auth(client):
    r = client.get("/api/ops-os/summary")
    assert r.status_code in (401, 403)


def test_ops_os_digital_twin_requires_auth(client):
    r = client.get("/api/ops-os/digital-twin")
    assert r.status_code in (401, 403)


def test_live_map_includes_camera_layer(client_and_db):
    client, _db_path = client_and_db
    login = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.get_json()['token']}"}
    created = client.post(
        "/api/companies",
        json={
            "name": "LiveMapCamCo",
            "contact": "x",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 0,
        },
        headers=headers,
    )
    assert created.status_code in (200, 201)
    payload = created.get_json() or {}
    cid = str((payload.get("company") or {}).get("id") or payload.get("id") or "")
    r = client.get(f"/api/ops-os/live-map?company_id={cid}", headers=headers)
    assert r.status_code == 200
    body = r.get_json() or {}
    assert "cameras" in body
    assert body.get("autoDial") is False
    assert "cameraAlerts" in (body.get("counts") or {})
