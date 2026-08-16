"""Worker mobile setup report (no secrets)."""
from __future__ import annotations

import pytest

from backend import server  # noqa: E402


@pytest.fixture()
def client(worker_client, tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setenv("BAUPASS_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("BAUPASS_AUDIT_SIGNING_KEY", "z" * 40)
    monkeypatch.setenv("BAUPASS_WORKER_JWT_SECRET", "y" * 40)
    monkeypatch.setenv("BAUPASS_TESTFLIGHT_URL", "https://testflight.apple.com/join/abc")
    monkeypatch.setenv("BAUPASS_DB_PATH", str(tmp_path / "baupass-test.db"))
    return worker_client


def test_collect_worker_mobile_setup_structure(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setenv("BAUPASS_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("BAUPASS_AUDIT_SIGNING_KEY", "z" * 40)
    monkeypatch.setenv("BAUPASS_WORKER_JWT_SECRET", "y" * 40)
    monkeypatch.setenv("BAUPASS_TESTFLIGHT_URL", "https://testflight.apple.com/join/abc")
    monkeypatch.setenv("BAUPASS_DB_PATH", str(tmp_path / "baupass-test.db"))
    monkeypatch.setenv("BAUPASS_PG_RUNTIME", "0")
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
