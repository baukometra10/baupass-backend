"""Pytest bootstrap — must run before `import server` in test modules."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BAUPASS_ENV", "testing")
os.environ.setdefault("BAUPASS_ENABLE_BACKGROUND_JOBS", "0")
os.environ.setdefault("BAUPASS_ENABLE_IMAP_POLLER", "0")
os.environ.setdefault("BAUPASS_SKIP_IMAP_POLL", "1")

from backend import server  # noqa: E402

TEST_COMPLIANCE_SIGNATURE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAD0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _prepare_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "baupass-test.db"
    monkeypatch.setenv("BAUPASS_DB_PATH", str(db_path))
    monkeypatch.setattr(server, "DB_PATH", db_path)
    server.request_rate_state.clear()
    server.failed_login_attempts.clear()
    server.init_db()
    server.app.config.update(TESTING=True)
    return db_path


@pytest.fixture()
def client_and_db(tmp_path, monkeypatch):
    db_path = _prepare_db(tmp_path, monkeypatch)
    with server.app.test_client() as client:
        yield client, db_path


@pytest.fixture()
def worker_client(tmp_path):
    db_path = tmp_path / "baupass-test.db"
    os.environ["BAUPASS_DB_PATH"] = str(db_path)
    server.DB_PATH = db_path
    server.request_rate_state.clear()
    server.failed_login_attempts.clear()
    server.init_db()
    server.app.config.update(TESTING=True)
    with server.app.test_client() as client:
        yield client
