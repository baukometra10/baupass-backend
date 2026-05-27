"""Physical Operations OS endpoints (smoke)."""
from __future__ import annotations


def test_ops_os_overview_requires_auth(client):
    r = client.get("/api/ops-os/overview")
    assert r.status_code in (401, 403)


def test_ops_os_digital_twin_requires_auth(client):
    r = client.get("/api/ops-os/digital-twin")
    assert r.status_code in (401, 403)
