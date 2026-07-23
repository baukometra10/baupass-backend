"""Worker-app site presence and offline site-leave sync."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from backend import server  # noqa: E402


@pytest.fixture()
def client(worker_client):
    return worker_client


@pytest.fixture
def site_app_session(client):
    with server.app.app_context():
        db = server.get_db()
        company_id = "cmp-site-app-test"
        try:
            db.execute(
                """
                INSERT INTO companies (
                    id, name, contact, plan, status, access_mode,
                    site_geofence_radius_meters, site_auto_checkin, site_auto_logout_on_leave
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (company_id, "Site App Co", "", "professional", "active", "site_app", 80, 1, 1),
            )
            db.commit()
        except Exception:
            db.rollback()
            db.execute(
                """
                UPDATE companies
                SET access_mode = ?, site_geofence_radius_meters = ?, site_auto_checkin = ?, site_auto_logout_on_leave = ?
                WHERE id = ?
                """,
                ("site_app", 80, 1, 1, company_id),
            )
            db.commit()

        db.execute("DELETE FROM geofences WHERE company_id = ?", (company_id,))
        db.execute(
            """
            INSERT INTO geofences (id, company_id, site_name, latitude, longitude, radius_meters, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "gf-site-app",
                company_id,
                "Hauptbaustelle",
                52.52,
                13.405,
                80,
                1,
                "2099-01-01T00:00:00Z",
            ),
        )

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
                company_id,
                "Site",
                "Worker",
                "INS-SITE",
                "worker",
                "arbeiter",
                "Hauptbaustelle",
                now,
                "active",
                "",
                "BP-SITE",
            ),
        )
        token = str(uuid.uuid4())
        expires = (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z"
        db.execute(
            "INSERT INTO worker_app_sessions (worker_id, token, expires_at, site_off_site_polls) VALUES (?, ?, ?, 0)",
            (worker_id, token, expires),
        )
        db.commit()
        return {
            "token": token,
            "worker_id": worker_id,
            "company_id": company_id,
            "on_site": {"latitude": 52.52, "longitude": 13.405, "accuracyMeters": 10},
            "off_site": {"latitude": 52.62, "longitude": 13.52, "accuracyMeters": 12},
        }


def test_site_presence_on_site_reports_distance(client, site_app_session):
    headers = {"Authorization": f"Bearer {site_app_session['token']}"}
    response = client.post(
        "/api/worker-app/site-presence",
        json={"location": site_app_session["on_site"]},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body.get("onSite") is True
    assert body.get("distanceMeters") is not None


def test_site_presence_off_site_requires_three_polls_before_leave(client, site_app_session):
    headers = {"Authorization": f"Bearer {site_app_session['token']}"}
    with server.app.app_context():
        db = server.get_db()
        log_id = str(uuid.uuid4())
        ts = datetime.utcnow().isoformat() + "Z"
        db.execute(
            """
            INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp, checked_in_late)
            VALUES (?, ?, 'check-in', 'site-app', 'test', ?, 0)
            """,
            (log_id, site_app_session["worker_id"], ts),
        )
        db.commit()

    for i in range(1, 3):
        response = client.post(
            "/api/worker-app/site-presence",
            json={"location": site_app_session["off_site"]},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body.get("siteLeaveApplied") is False
        assert int(body.get("offSitePolls") or 0) == i
        assert int(body.get("offSitePollsRequired") or 0) == 3

    response = client.post(
        "/api/worker-app/site-presence",
        json={"location": site_app_session["off_site"]},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body.get("siteLeaveApplied") is True
    assert int(body.get("offSitePolls") or 0) == 3
    assert body.get("checkoutLogId") or body.get("siteLeaveLogId")


def test_offline_site_leave_replay_creates_checkout(client, site_app_session):
    headers = {"Authorization": f"Bearer {site_app_session['token']}"}
    with server.app.app_context():
        db = server.get_db()
        log_id = str(uuid.uuid4())
        ts = datetime.utcnow().isoformat() + "Z"
        db.execute(
            """
            INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp, checked_in_late)
            VALUES (?, ?, 'check-in', 'site-app', 'offline-test', ?, 0)
            """,
            (log_id, site_app_session["worker_id"], ts),
        )
        db.commit()

    occurred = datetime.utcnow().isoformat() + "Z"
    response = client.post(
        "/api/worker-app/offline-events",
        json={
            "events": [
                {
                    "type": "site_leave",
                    "occurredAt": occurred,
                    "clientEventId": "site-leave-test-1",
                    "location": site_app_session["off_site"],
                }
            ]
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body.get("ok") is True
    results = body.get("results") or []
    assert results
    assert results[0].get("checkoutLogId") or results[0].get("siteLeaveLogId")

    with server.app.app_context():
        db = server.get_db()
        checkout = db.execute(
            """
            SELECT id FROM access_logs
            WHERE worker_id = ? AND direction = 'check-out'
            ORDER BY timestamp DESC LIMIT 1
            """,
            (site_app_session["worker_id"],),
        ).fetchone()
        assert checkout is not None


def test_access_summary_includes_late_checkins_today(client, site_app_session):
    with server.app.app_context():
        db = server.get_db()
        worker_id = site_app_session["worker_id"]
        ts = datetime.utcnow().isoformat() + "Z"
        db.execute(
            """
            INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp, checked_in_late)
            VALUES (?, ?, 'check-in', 'gate', '', ?, 1)
            """,
            (str(uuid.uuid4()), worker_id, ts),
        )
        db.commit()

        admin_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO users (id, username, password_hash, role, company_id, name, email)
            VALUES (?, 'late-admin', ?, 'company-admin', ?, 'Late Admin', 'late@test.local')
            """,
            (admin_id, server.generate_password_hash("secret"), site_app_session["company_id"]),
        )
        db.commit()

    login = client.post(
        "/api/login",
        json={"username": "late-admin", "password": "secret"},
    )
    assert login.status_code == 200
    token = login.get_json().get("token")
    summary = client.get(
        "/api/access-logs/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert summary.status_code == 200
    body = summary.get_json()
    assert int(body.get("lateCheckInsToday") or 0) >= 1
    assert int(body.get("checkInsToday") or 0) >= 1
    assert body.get("hasActivityToday") is True
    assert body.get("today")
    hourly_sum = sum(int(h.get("checkIn") or 0) for h in (body.get("hourly") or []))
    assert hourly_sum == int(body.get("checkInsToday") or 0)
