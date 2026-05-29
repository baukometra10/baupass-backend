"""Worker mobile setup report (no secrets)."""
from __future__ import annotations

import os

import pytest

from backend import server  # noqa: E402


@pytest.fixture()
def client(worker_client):
    os.environ["PUBLIC_BASE_URL"] = "https://example.test"
    os.environ["BAUPASS_SECRET_KEY"] = "x" * 40
    os.environ["BAUPASS_WORKER_JWT_SECRET"] = "y" * 40
    os.environ["BAUPASS_TESTFLIGHT_URL"] = "https://testflight.apple.com/join/abc"
    return worker_client


def test_collect_worker_mobile_setup_structure(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setenv("BAUPASS_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("BAUPASS_WORKER_JWT_SECRET", "y" * 40)
    monkeypatch.setenv("BAUPASS_TESTFLIGHT_URL", "https://testflight.apple.com/join/abc")
    from backend.app.platform.mobile_worker_setup import collect_worker_mobile_setup

    report = collect_worker_mobile_setup()
    assert report["workerAppKind"] == "hybrid_flutter"
    assert report["publicBaseUrl"] == "https://example.test"
    assert "envKeys" in report
    assert report["readiness"]["coreBackend"] is True
    assert report["readiness"]["iphoneTestFlight"] is True
    assert "BAUPASS_TESTFLIGHT_URL" not in report["missingRequired"]


def test_worker_mobile_setup_http(client):
    r = client.get("/api/worker-app/mobile-setup")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("workerAppKind") == "hybrid_flutter"
    assert "readiness" in data
