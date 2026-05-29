"""Worker mobile setup report (no secrets)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BAUPASS_ENABLE_BACKGROUND_JOBS", "0")
os.environ.setdefault("BAUPASS_ENABLE_IMAP_POLLER", "0")
os.environ["BAUPASS_DB_PATH"] = str(Path(__file__).resolve().parent / "baupass-test.db")
os.environ["PUBLIC_BASE_URL"] = "https://example.test"
os.environ["BAUPASS_SECRET_KEY"] = "x" * 40
os.environ["BAUPASS_WORKER_JWT_SECRET"] = "y" * 40
os.environ["BAUPASS_TESTFLIGHT_URL"] = "https://testflight.apple.com/join/abc"

from backend import server  # noqa: E402

server.DB_PATH = Path(os.environ["BAUPASS_DB_PATH"])


@pytest.fixture(scope="module")
def client():
    server.init_db()
    return server.app.test_client()


def test_collect_worker_mobile_setup_structure():
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
