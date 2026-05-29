"""Worker-app offline event sync (pytest)."""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BAUPASS_ENABLE_BACKGROUND_JOBS", "0")
os.environ.setdefault("BAUPASS_ENABLE_IMAP_POLLER", "0")
os.environ["BAUPASS_DB_PATH"] = str(Path(__file__).resolve().parent / "baupass-test.db")

from backend import server  # noqa: E402

server.DB_PATH = Path(os.environ["BAUPASS_DB_PATH"])


@pytest.fixture(scope="module")
def client():
    server.init_db()
    return server.app.test_client()


@pytest.fixture
def worker_session(client):
    with server.app.app_context():
        db = server.get_db()
        try:
            db.execute(
                "INSERT INTO settings (id, platform_name, operator_name, turnstile_endpoint, rental_model) "
                "VALUES (1, 'Test', 'Operator', '/', 'r')"
            )
            db.commit()
        except Exception:
            db.rollback()
        try:
            db.execute(
                "INSERT INTO companies (id, name, contact, plan, status) VALUES (?, ?, ?, ?, ?)",
                ("1", "TestCo", "", "starter", "active"),
            )
            db.commit()
        except Exception:
            db.rollback()
            db.execute("UPDATE companies SET plan = ? WHERE id = ?", ("starter", "1"))
            db.commit()

        worker_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, status, photo_data, badge_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                worker_id,
                "1",
                "E2E",
                "Worker",
                "INS-000",
                "worker",
                "arbeiter",
                "site-a",
                now,
                "active",
                "",
                "BP-TEST",
            ),
        )
        token = str(uuid.uuid4())
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
        db.execute(
            "INSERT INTO worker_app_sessions (worker_id, token, expires_at) VALUES (?, ?, ?)",
            (worker_id, token, expires),
        )
        db.commit()
        yield token


def test_offline_events_sync(client, worker_session):
    token = worker_session
    payload = {
        "events": [
            {
                "type": "offline_login",
                "occurredAt": datetime.utcnow().isoformat() + "Z",
                "distanceMeters": 10,
            }
        ]
    }
    response = client.post(
        "/api/worker-app/offline-events",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body.get("ok") is True
    assert body.get("stored", 0) >= 1


def test_worker_app_login_missing_credentials(client):
    response = client.post("/api/worker-app/login", json={})
    assert response.status_code == 400
    assert response.get_json().get("error") == "missing_worker_app_credentials"


def test_dynamic_qr_requires_session(client, worker_session):
    token = worker_session
    response = client.get(
        "/api/worker-app/dynamic-qr",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body.get("qrToken")
    assert body.get("badgeId") == "BP-TEST"


def test_team_snapshot_open_checkouts_not_always_present(client, worker_session):
    """openCheckouts counts unmatched check-ins; can differ from present."""
    token = worker_session
    with server.app.app_context():
        db = server.get_db()
        session = db.execute(
            "SELECT worker_id FROM worker_app_sessions WHERE token = ?",
            (token,),
        ).fetchone()
        worker = db.execute("SELECT * FROM workers WHERE id = ?", (session["worker_id"],)).fetchone()
        snapshot = server.build_worker_team_snapshot(db, worker)
    assert "openCheckouts" in snapshot
    assert "present" in snapshot
    assert snapshot["openCheckouts"] >= 0
    assert snapshot["present"] >= 0
