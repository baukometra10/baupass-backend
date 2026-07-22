"""Tests for consecutive late streaks and forecast notify."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from backend.app.platform.workforce.late_streak import (
    LATE_STREAK_THRESHOLD,
    count_consecutive_late_checkins,
    evaluate_late_streak_after_checkin,
    list_repeated_late_workers,
)


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "late-streak.db"
    monkeypatch.setenv("BAUPASS_DB_PATH", str(db_path))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE workers (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            worker_type TEXT NOT NULL DEFAULT 'worker',
            first_name TEXT,
            last_name TEXT,
            deleted_at TEXT
        );
        CREATE TABLE access_logs (
            id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            gate TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            timestamp TEXT NOT NULL,
            checked_in_late INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE companies (
            id TEXT PRIMARY KEY,
            billing_email TEXT NOT NULL DEFAULT '',
            invoice_email_lang TEXT NOT NULL DEFAULT 'de',
            deleted_at TEXT,
            status TEXT NOT NULL DEFAULT 'aktiv',
            report_timezone TEXT NOT NULL DEFAULT 'Europe/Berlin'
        );
        CREATE TABLE system_alerts (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            resolved_at TEXT
        );
        CREATE TABLE settings (
            id INTEGER PRIMARY KEY,
            smtp_sender_email TEXT NOT NULL DEFAULT '',
            smtp_sender_name TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            company_id TEXT,
            role TEXT,
            email TEXT
        );
        INSERT INTO companies (id, billing_email) VALUES ('co-1', 'boss@example.com');
        INSERT INTO settings (id) VALUES (1);
        INSERT INTO workers (id, company_id, first_name, last_name)
        VALUES ('wrk-1', 'co-1', 'Late', 'Worker');
        """
    )
    conn.commit()
    yield conn
    conn.close()


def _insert_checkin(db, *, day: date, late: bool, idx: int = 0):
    ts = datetime(day.year, day.month, day.day, 8 + idx, 30).isoformat()
    db.execute(
        """
        INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp, checked_in_late)
        VALUES (?, 'wrk-1', 'check-in', 'Gate', '', ?, ?)
        """,
        (f"log-{day.isoformat()}-{idx}", ts, 1 if late else 0),
    )
    db.commit()


def test_streak_counts_three_consecutive_lates(db_conn):
    today = date(2026, 6, 10)
    _insert_checkin(db_conn, day=today - timedelta(days=2), late=True)
    _insert_checkin(db_conn, day=today - timedelta(days=1), late=True)
    _insert_checkin(db_conn, day=today, late=True)
    streak = count_consecutive_late_checkins(db_conn, "wrk-1", as_of=today)
    assert streak == 3


def test_streak_breaks_on_on_time_day(db_conn):
    today = date(2026, 6, 10)
    _insert_checkin(db_conn, day=today - timedelta(days=3), late=True)
    _insert_checkin(db_conn, day=today - timedelta(days=2), late=False)
    _insert_checkin(db_conn, day=today - timedelta(days=1), late=True)
    _insert_checkin(db_conn, day=today, late=True)
    streak = count_consecutive_late_checkins(db_conn, "wrk-1", as_of=today)
    assert streak == 2


def test_evaluate_triggers_at_threshold(db_conn):
    today = date(2026, 6, 10)
    for i in range(LATE_STREAK_THRESHOLD):
        _insert_checkin(db_conn, day=today - timedelta(days=i), late=True)
    worker = db_conn.execute("SELECT * FROM workers WHERE id = 'wrk-1'").fetchone()
    # evaluate uses date.today(); seed relative to real today instead
    real_today = date.today()
    db_conn.execute("DELETE FROM access_logs")
    for i in range(LATE_STREAK_THRESHOLD):
        _insert_checkin(db_conn, day=real_today - timedelta(days=i), late=True)
    payload = evaluate_late_streak_after_checkin(db_conn, worker, late=True)
    assert payload is not None
    assert payload["streak"] >= LATE_STREAK_THRESHOLD
    assert payload["workerId"] == "wrk-1"


def test_evaluate_none_below_threshold(db_conn):
    real_today = date.today()
    _insert_checkin(db_conn, day=real_today, late=True)
    _insert_checkin(db_conn, day=real_today - timedelta(days=1), late=True)
    worker = db_conn.execute("SELECT * FROM workers WHERE id = 'wrk-1'").fetchone()
    assert evaluate_late_streak_after_checkin(db_conn, worker, late=True) is None
    assert evaluate_late_streak_after_checkin(db_conn, worker, late=False) is None


def test_list_repeated_late_workers(db_conn):
    real_today = date.today()
    for i in range(3):
        _insert_checkin(db_conn, day=real_today - timedelta(days=i), late=True)
    rows = list_repeated_late_workers(db_conn, "co-1", min_streak=3, limit=5)
    assert len(rows) == 1
    assert rows[0]["streak"] >= 3


def test_notify_repeated_late_dedups(client_and_db, monkeypatch):
    from backend import server
    from backend.app.platform.notifications.company_mitteilung import (
        notify_company_repeated_late_checkin,
    )

    _client, _db_path = client_and_db
    monkeypatch.setattr(server, "_send_via_any_api", lambda *a, **k: (True, None, "test"))
    monkeypatch.setattr(
        "backend.app.platform.inbox.events.notify_inbox_changed",
        MagicMock(),
    )
    monkeypatch.setattr(
        "backend.app.platform.push.admin_delivery.deliver_admin_push",
        MagicMock(return_value={"ok": True, "sent": 0}),
    )
    with server.app.app_context():
        db = server.get_db()
        db.execute(
            "UPDATE companies SET billing_email = ? WHERE id = ?",
            ("boss@example.com", "cmp-default"),
        )
        db.commit()
        first = notify_company_repeated_late_checkin(
            db,
            company_id="cmp-default",
            worker_id="wrk-1",
            worker_name="Late Worker",
            streak=3,
        )
        second = notify_company_repeated_late_checkin(
            db,
            company_id="cmp-default",
            worker_id="wrk-1",
            worker_name="Late Worker",
            streak=4,
        )
        assert first.get("deduped") is False
        assert first.get("alertId")
        assert second.get("deduped") is True


def test_forecast_notify_force(client_and_db, monkeypatch):
    from backend import server
    from backend.app.platform.predictions.forecast_notify_job import run_forecast_notify_cycle

    _client, _db_path = client_and_db
    monkeypatch.setattr(server, "_send_via_any_api", lambda *a, **k: (True, None, "test"))
    monkeypatch.setattr(
        "backend.app.platform.inbox.events.notify_inbox_changed",
        MagicMock(),
    )
    monkeypatch.setattr(
        "backend.app.platform.predictions.engine.build_tomorrow_forecast",
        lambda db, cid: {
            "date": "2026-06-11",
            "expectedOnSite": 8,
            "expectedAbsent": 3,
            "drivers": [{"type": "approved_leave", "items": [{"name": "A B"}]}],
        },
    )
    with server.app.app_context():
        db = server.get_db()
        db.execute(
            "UPDATE companies SET billing_email = ? WHERE id = ?",
            ("boss@example.com", "cmp-default"),
        )
        db.commit()
        result = run_forecast_notify_cycle(db, force=True)
        assert result["ok"] is True
        assert result["notified"] >= 1
        alerts = db.execute(
            "SELECT code FROM system_alerts WHERE code = ?",
            ("tomorrow_attendance_forecast",),
        ).fetchall()
        assert len(alerts) >= 1
        # Second run same day should dedupe
        result2 = run_forecast_notify_cycle(db, force=True)
        assert result2["skipped"] >= 1 or result2["notified"] == 0
