"""Worker-app NFC attendance endpoint (pytest)."""
from __future__ import annotations

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


@pytest.fixture(scope="module")
def client():
    server.init_db()
    return server.app.test_client()


@pytest.fixture
def nfc_worker_session(client):
    with server.app.app_context():
        db = server.get_db()
        company_id = "cmp-nfc-test"
        try:
            db.execute(
                "INSERT INTO companies (id, name, contact, plan, status) VALUES (?, ?, ?, ?, ?)",
                (company_id, "NFC Test Co", "", "starter", "active"),
            )
            db.commit()
        except Exception:
            db.rollback()
            db.execute("UPDATE companies SET plan = ? WHERE id = ?", ("starter", company_id))
            db.commit()

        worker_id = str(uuid.uuid4())
        card_uid = "04A1B2C3D4E5F6"
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, status, photo_data,
                badge_id, physical_card_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                worker_id,
                company_id,
                "NFC",
                "Worker",
                "INS-NFC",
                "worker",
                "arbeiter",
                "site-a",
                datetime.utcnow().isoformat() + "Z",
                "aktiv",
                "",
                "BP-NFC-1",
                card_uid,
            ),
        )
        token = str(uuid.uuid4())
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
        db.execute(
            "INSERT INTO worker_app_sessions (worker_id, token, expires_at) VALUES (?, ?, ?)",
            (worker_id, token, expires),
        )
        db.commit()
        yield {
            "token": token,
            "worker_id": worker_id,
            "card_uid": card_uid,
            "card_uid_formatted": "04:A1:B2:C3:D4:E5:F6",
        }


def test_nfc_attendance_requires_session(client):
    response = client.post("/api/worker-app/attendance/nfc", json={"nfcUid": "04A1"})
    assert response.status_code == 401


def test_nfc_attendance_check_in_and_out(client, nfc_worker_session):
    token = nfc_worker_session["token"]
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        "/api/worker-app/attendance/nfc",
        json={"nfcUid": nfc_worker_session["card_uid_formatted"], "direction": "auto"},
        headers=headers,
    )
    assert first.status_code == 200
    body = first.get_json()
    assert body.get("ok") is True
    assert body.get("direction") == "check-in"
    assert body.get("logId")

    second = client.post(
        "/api/worker-app/attendance/nfc",
        json={"nfcUid": nfc_worker_session["card_uid"], "direction": "auto"},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.get_json().get("direction") == "check-out"


def test_offline_nfc_attendance_sync(client, nfc_worker_session):
    token = nfc_worker_session["token"]
    headers = {"Authorization": f"Bearer {token}"}
    client_event_id = "offline-test-1"
    response = client.post(
        "/api/worker-app/offline-events",
        json={
            "events": [
                {
                    "type": "nfc_attendance",
                    "clientEventId": client_event_id,
                    "nfcUid": nfc_worker_session["card_uid_formatted"],
                    "direction": "check-in",
                    "occurredAt": "2026-05-27T06:00:00.000Z",
                }
            ]
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body.get("stored") == 1
    results = body.get("results") or []
    assert results[0].get("ok") is True
    assert results[0].get("direction") == "check-in"

    replay = client.post(
        "/api/worker-app/offline-events",
        json={
            "events": [
                {
                    "type": "nfc_attendance",
                    "clientEventId": client_event_id,
                    "nfcUid": nfc_worker_session["card_uid"],
                    "direction": "check-in",
                    "occurredAt": "2026-05-27T06:00:00.000Z",
                }
            ]
        },
        headers=headers,
    )
    assert replay.status_code == 200
    assert replay.get_json()["results"][0].get("replay") is True


def test_nfc_attendance_uid_mismatch(client, nfc_worker_session):
    token = nfc_worker_session["token"]
    response = client.post(
        "/api/worker-app/attendance/nfc",
        json={"nfcUid": "DEADBEEF"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.get_json().get("error") == "nfc_uid_mismatch"
