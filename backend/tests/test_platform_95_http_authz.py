"""HTTP authz / IDOR checks for Platform 95 closeout surfaces."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from backend import server  # noqa: F401


def _super_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def _company_admin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "firma", "password": "1234", "loginScope": "company-admin"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    return {"Authorization": f"Bearer {payload['token']}"}, payload


def test_camera_legal_requires_auth(client_and_db):
    client, _ = client_and_db
    assert client.get("/api/ops-os/camera-legal").status_code in {401, 403}
    assert client.post("/api/ops-os/camera-legal", json={}).status_code in {401, 403}


def test_camera_legal_ignores_body_company_id_idor(client_and_db):
    client, _ = client_and_db
    headers, login = _company_admin_headers(client)
    own = str(login["user"]["company_id"])
    foreign = "cmp-idor-other" if own != "cmp-idor-other" else "cmp-idor-alt"

    resp = client.post(
        "/api/ops-os/camera-legal",
        headers=headers,
        json={
            "companyId": foreign,
            "recordingEnabled": True,
            "legalAck": True,
            "legalBasisText": "Betriebsvereinbarung IDOR-Test 2026",
            "validUntil": "2099-01-01T00:00:00Z",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json() or {}
    assert body.get("companyId") == own
    assert body.get("companyId") != foreign

    foreign_get = client.get(
        f"/api/ops-os/camera-legal?company_id={foreign}",
        headers=headers,
    )
    assert foreign_get.status_code == 200
    # company-admin cannot switch company via query — still own tenant.
    assert (foreign_get.get_json() or {}).get("companyId") == own


def test_partner_readiness_requires_auth(client_and_db):
    client, _ = client_and_db
    assert client.get("/api/integrations/partner/readiness").status_code in {401, 403}


def test_personio_sync_disabled_without_flag(client_and_db, monkeypatch):
    client, _ = client_and_db
    monkeypatch.delenv("BAUPASS_PERSONIO_ENABLED", raising=False)
    headers, _ = _company_admin_headers(client)
    resp = client.post("/api/integrations/personio/sync", headers=headers, json={})
    assert resp.status_code == 403
    assert (resp.get_json() or {}).get("error") == "personio_disabled"


def test_personio_webhook_rejects_bad_signature(client_and_db, monkeypatch):
    client, _ = client_and_db
    monkeypatch.setenv("BAUPASS_PERSONIO_ENABLED", "1")
    monkeypatch.setenv("PERSONIO_WEBHOOK_SECRET", "test-secret-personio")
    body = json.dumps({"data": []}).encode("utf-8")
    bad = client.post(
        "/api/integrations/personio/webhook?company_id=cmp-default",
        data=body,
        headers={"Content-Type": "application/json", "X-Personio-Signature": "wrong"},
    )
    assert bad.status_code == 401

    digest = hmac.new(b"test-secret-personio", body, hashlib.sha256).hexdigest()
    ok = client.post(
        "/api/integrations/personio/webhook?company_id=cmp-default",
        data=body,
        headers={"Content-Type": "application/json", "X-Personio-Signature": digest},
    )
    assert ok.status_code == 200
    assert (ok.get_json() or {}).get("ok") is True


def test_partner_package_scoped_to_company_admin(client_and_db):
    client, _ = client_and_db
    headers, login = _company_admin_headers(client)
    own = str(login["user"]["company_id"])
    resp = client.get(
        f"/api/integrations/partner/readiness?company_id=cmp-foreign-xyz",
        headers=headers,
    )
    assert resp.status_code == 200
    # Readiness is keyed by auth company; foreign query must not escalate.
    data = resp.get_json() or {}
    # partner_readiness_summary returns companyId when present
    if "companyId" in data:
        assert data["companyId"] == own
