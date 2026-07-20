"""Presence session pairing for check-in/app-login and check-out/app-logout."""

from datetime import datetime, timezone

from backend.app.platform.physical_operations._common import (
    count_on_site,
    is_worker_present_on_site_today,
    minutes_between_access_timestamps,
    pair_presence_sessions,
    pair_work_attendance_sessions,
    today_prefix,
    today_work_minutes,
    total_presence_minutes,
    total_work_attendance_minutes,
)


def test_today_prefix_uses_berlin_not_utc():
    # 23:30 UTC on Jan 15 = 00:30 CET on Jan 16 in Berlin
    ref = datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc)
    assert today_prefix(reference=ref) == "2026-01-16"


def test_server_access_today_prefix_matches_common():
    from backend.server import access_today_prefix

    ref = datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc)
    assert access_today_prefix(ref) == today_prefix(reference=ref)


def test_app_login_logout_pairing_counts_short_session():
    events = [
        {"direction": "app-login", "timestamp": "2026-06-24T08:00:00", "gate": "Site A"},
        {"direction": "app-logout", "timestamp": "2026-06-24T08:00:45", "gate": "Site A"},
    ]
    sessions = pair_presence_sessions(events)
    assert len(sessions) == 1
    assert sessions[0]["durationMinutes"] == 1
    assert total_presence_minutes(events) == 1


def test_mixed_check_in_and_app_logout():
    events = [
        {"direction": "check-in", "timestamp": "2026-06-24T07:00:00", "gate": "Gate 1"},
        {"direction": "app-logout", "timestamp": "2026-06-24T09:30:00", "gate": "Site GPS"},
    ]
    sessions = pair_presence_sessions(events)
    assert len(sessions) == 1
    assert sessions[0]["durationMinutes"] == 150
    assert sessions[0]["checkIn"] == "2026-06-24T07:00:00"
    assert sessions[0]["checkOut"] == "2026-06-24T09:30:00"


def test_open_session_has_no_closed_duration():
    events = [
        {"direction": "app-login", "timestamp": "2026-06-24T10:00:00", "gate": "Site A"},
    ]
    sessions = pair_presence_sessions(events)
    assert len(sessions) == 1
    assert sessions[0]["checkOut"] is None
    assert sessions[0]["durationMinutes"] is None


def test_minutes_between_rounds_up():
    assert minutes_between_access_timestamps("2026-06-24T10:00:00", "2026-06-24T10:00:01") == 1
    assert minutes_between_access_timestamps("2026-06-24T10:00:00", "2026-06-24T10:59:00") == 59


def test_minutes_between_utc_z_and_naive_berlin_wall():
    # 19:11 UTC == 21:11 Berlin (CEST); local auto-checkout at 02:00 next day.
    assert (
        minutes_between_access_timestamps("2026-07-18T19:11:00Z", "2026-07-19T02:00:00")
        == 289
    )


def test_pair_mixed_z_and_naive_sort_order():
    events = [
        {"direction": "check-out", "timestamp": "2026-07-19T00:00:00", "gate": "System"},
        {"direction": "check-in", "timestamp": "2026-07-18T21:11:54Z", "gate": "App"},
    ]
    sessions = pair_presence_sessions(events)
    assert len(sessions) == 1
    assert sessions[0]["checkIn"] == "2026-07-18T21:11:54Z"
    assert sessions[0]["checkOut"] == "2026-07-19T00:00:00"
    # 21:11Z = 23:11 Berlin → 00:00 Berlin next day = 49 minutes
    assert sessions[0]["durationMinutes"] == 49


def test_work_attendance_ignores_app_login_for_hours():
    events = [
        {"direction": "check-in", "timestamp": "2026-06-24T07:00:00", "gate": "Gate"},
        {"direction": "check-out", "timestamp": "2026-06-24T15:00:00", "gate": "Gate"},
        {"direction": "app-login", "timestamp": "2026-06-24T16:00:00", "gate": "Site"},
    ]
    assert total_work_attendance_minutes(events) == 480
    sessions = pair_work_attendance_sessions(events)
    assert len(sessions) == 1
    assert sessions[0]["durationMinutes"] == 480


def test_app_login_after_checkout_does_not_add_open_work_hours():
    events = [
        {"direction": "check-in", "timestamp": "2026-07-09T06:00:00", "gate": "Gate"},
        {"direction": "check-out", "timestamp": "2026-07-09T14:00:00", "gate": "Gate"},
        {"direction": "app-login", "timestamp": "2026-07-09T16:00:00", "gate": "Site"},
    ]
    assert total_work_attendance_minutes(events) == 480
    assert today_work_minutes(events, day_prefix="2026-07-09") == 480


def test_open_checkin_closed_by_later_app_logout(client_and_db):
    _client, _db_path = client_and_db
    from backend import server

    today = today_prefix()
    with server.app.app_context():
        db = server.get_db()
        company = db.execute(
            "SELECT id FROM companies WHERE deleted_at IS NULL LIMIT 1"
        ).fetchone()
        assert company is not None
        company_id = company["id"]
        worker_id = "wrk-presence-logout-test"
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, status, photo_data, badge_id
            ) VALUES (?, ?, 'P', 'Test', 'INS-PRE', 'worker', 'mitarbeiter', 'Site',
                      '2099-01-01T00:00:00Z', 'aktiv', '', 'BT-PRE')
            """,
            (worker_id, company_id),
        )
        db.execute(
            """
            INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp, checked_in_late)
            VALUES (?, ?, 'check-in', 'Gate', '', ?, 0)
            """,
            ("log-in-pre", worker_id, f"{today}T08:00:00"),
        )
        db.execute(
            """
            INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp, checked_in_late)
            VALUES (?, ?, 'app-logout', 'GPS', '', ?, 0)
            """,
            ("log-out-pre", worker_id, f"{today}T10:00:00"),
        )
        db.commit()
        assert is_worker_present_on_site_today(db, worker_id, today) is False
        assert count_on_site(db, company_id, today) == 0
