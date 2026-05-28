"""Worker login device binding + JWT (pytest)."""
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
os.environ["BAUPASS_DB_PATH"] = str(Path(__file__).resolve().parent / "baupass-device-test.db")
os.environ["BAUPASS_WORKER_DEVICE_BINDING"] = "1"
os.environ["BAUPASS_WORKER_JWT"] = "1"
os.environ["BAUPASS_WORKER_JWT_SECRET"] = "test-worker-jwt-secret"

from backend import server  # noqa: E402
from backend.app.platform.security.worker_devices import verify_worker_access_jwt  # noqa: E402


@pytest.fixture(scope="module")
def client():
    server.init_db()
    return server.app.test_client()


def _seed_worker(db, badge_id="BP-DEV-1", pin="1234"):
    company_id = "cmp-device-test"
    try:
        db.execute(
            "INSERT INTO companies (id, name, contact, plan, status) VALUES (?, ?, ?, ?, ?)",
            (company_id, "Device Test", "", "starter", "active"),
        )
        db.commit()
    except Exception:
        db.rollback()

    worker_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO workers (
            id, company_id, first_name, last_name, insurance_number,
            worker_type, role, site, valid_until, status, photo_data,
            badge_id, badge_id_lookup, badge_pin_hash, physical_card_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            worker_id,
            company_id,
            "Dev",
            "Worker",
            "INS-DEV",
            "worker",
            "arbeiter",
            "site-a",
            datetime.utcnow().isoformat() + "Z",
            "aktiv",
            "",
            badge_id,
            badge_id,
            server.generate_password_hash(pin),
            "04A1B2C3D4E5F6",
        ),
    )
    db.commit()
    return worker_id, badge_id, pin


def test_login_binds_device_and_issues_jwt(client):
    with server.app.app_context():
        db = server.get_db()
        _, badge_id, pin = _seed_worker(db)

    response = client.post(
        "/api/worker-app/login",
        json={
            "badgeId": badge_id,
            "badgePin": pin,
            "device": {
                "fingerprint": "test-device-fp-001",
                "name": "Test Phone",
                "platform": "android",
            },
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body.get("token")
    assert body.get("jwt")
    assert body.get("deviceId", "").startswith("wbd-")

    claims = verify_worker_access_jwt(body["jwt"])
    assert claims is not None
    assert claims["device_id"] == body["deviceId"]

    me = client.get(
        "/api/worker-app/me",
        headers={
            "Authorization": f"Bearer {body['jwt']}",
            "X-Device-Id": body["deviceId"],
        },
    )
    assert me.status_code == 200

    me_bad_device = client.get(
        "/api/worker-app/me",
        headers={
            "Authorization": f"Bearer {body['jwt']}",
            "X-Device-Id": "wbd-wrong-device",
        },
    )
    assert me_bad_device.status_code == 403
    assert me_bad_device.get_json().get("error") == "device_not_bound"
