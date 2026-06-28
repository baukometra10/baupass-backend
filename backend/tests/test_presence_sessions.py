"""Presence session pairing for check-in/app-login and check-out/app-logout."""

from backend.app.platform.physical_operations._common import (
    minutes_between_access_timestamps,
    pair_presence_sessions,
    total_presence_minutes,
)


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
