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
