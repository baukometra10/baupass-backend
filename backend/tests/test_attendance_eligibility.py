"""Tests for worker auto-attendance eligibility rules."""
from __future__ import annotations

from datetime import date

import pytest

from backend.app.platform.workforce.attendance_eligibility import worker_may_auto_attend_today


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "attendance.db"
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
            last_name TEXT
        );
        CREATE TABLE leave_requests (
            id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            status TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL
        );
        CREATE TABLE worker_deployment_days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL,
            worker_id TEXT NOT NULL,
            work_date TEXT NOT NULL,
            location_label TEXT NOT NULL DEFAULT '',
            shift_start TEXT NOT NULL DEFAULT '',
            shift_end TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE worker_deployment_day_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL,
            worker_id TEXT NOT NULL,
            work_date TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE deployment_month_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft'
        );
        CREATE TABLE companies (
            id TEXT PRIMARY KEY,
            work_start_time TEXT NOT NULL DEFAULT '',
            work_end_time TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE settings (
            id INTEGER PRIMARY KEY,
            work_start_time TEXT NOT NULL DEFAULT '',
            work_end_time TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO companies (id, work_start_time, work_end_time)
        VALUES ('co-1', '08:00', '17:00');
        INSERT INTO settings (id) VALUES (1);
        INSERT INTO workers (id, company_id, worker_type, first_name, last_name)
        VALUES ('wrk-1', 'co-1', 'worker', 'Max', 'Muster');
        """
    )
    conn.commit()
    yield conn
    conn.close()


def test_blocks_free_day_when_plan_has_assignments(db_conn):
    db_conn.execute(
        """
        INSERT INTO worker_deployment_days (company_id, worker_id, work_date, location_label)
        VALUES ('co-1', 'wrk-1', '2026-06-10', 'Baustelle Nord')
        """
    )
    db_conn.commit()
    worker = db_conn.execute("SELECT * FROM workers WHERE id = 'wrk-1'").fetchone()
    result = worker_may_auto_attend_today(
        db_conn, worker, target_date=date(2026, 6, 9), now=__import__("datetime").datetime(2026, 6, 9, 8, 0)
    )
    assert result["ok"] is False
    assert result["reason"] == "not_scheduled_today"
    assert result["dayType"] == "free"


def test_treats_frei_location_marker_as_free_day(db_conn):
    db_conn.execute(
        """
        INSERT INTO worker_deployment_days (company_id, worker_id, work_date, location_label)
        VALUES ('co-1', 'wrk-1', '2026-06-09', 'Frei')
        """
    )
    db_conn.execute(
        """
        INSERT INTO worker_deployment_days (company_id, worker_id, work_date, location_label)
        VALUES ('co-1', 'wrk-1', '2026-06-10', 'Baustelle Nord')
        """
    )
    db_conn.commit()
    worker = db_conn.execute("SELECT * FROM workers WHERE id = 'wrk-1'").fetchone()
    result = worker_may_auto_attend_today(
        db_conn, worker, target_date=date(2026, 6, 9), now=__import__("datetime").datetime(2026, 6, 9, 8, 0)
    )
    assert result["ok"] is False
    assert result["reason"] == "not_scheduled_today"


def test_allows_scheduled_day(db_conn):
    db_conn.execute(
        """
        INSERT INTO worker_deployment_days (company_id, worker_id, work_date, location_label, shift_start, shift_end)
        VALUES ('co-1', 'wrk-1', '2026-06-09', 'Baustelle Nord', '07:00', '16:00')
        """
    )
    db_conn.commit()
    worker = db_conn.execute("SELECT * FROM workers WHERE id = 'wrk-1'").fetchone()
    result = worker_may_auto_attend_today(
        db_conn, worker, target_date=date(2026, 6, 9), now=__import__("datetime").datetime(2026, 6, 9, 8, 0)
    )
    assert result["ok"] is True
    assert result["dayType"] == "scheduled"


def test_blocks_approved_leave(db_conn):
    db_conn.execute(
        """
        INSERT INTO leave_requests (id, worker_id, status, start_date, end_date)
        VALUES ('lr-1', 'wrk-1', 'genehmigt', '2026-06-09', '2026-06-12')
        """
    )
    db_conn.commit()
    worker = db_conn.execute("SELECT * FROM workers WHERE id = 'wrk-1'").fetchone()
    result = worker_may_auto_attend_today(
        db_conn, worker, target_date=date(2026, 6, 10), now=__import__("datetime").datetime(2026, 6, 10, 8, 0)
    )
    assert result["ok"] is False
    assert result["reason"] == "on_approved_leave"


def test_blocks_declined_assignment(db_conn):
    db_conn.execute(
        """
        INSERT INTO worker_deployment_days (company_id, worker_id, work_date, location_label)
        VALUES ('co-1', 'wrk-1', '2026-06-09', 'Baustelle Nord')
        """
    )
    db_conn.execute(
        """
        INSERT INTO worker_deployment_day_responses (company_id, worker_id, work_date, status)
        VALUES ('co-1', 'wrk-1', '2026-06-09', 'declined')
        """
    )
    db_conn.commit()
    worker = db_conn.execute("SELECT * FROM workers WHERE id = 'wrk-1'").fetchone()
    result = worker_may_auto_attend_today(
        db_conn, worker, target_date=date(2026, 6, 9), now=__import__("datetime").datetime(2026, 6, 9, 8, 0)
    )
    assert result["ok"] is False
    assert result["reason"] == "deployment_declined"


def test_blocks_outside_company_work_hours(db_conn):
    worker = db_conn.execute("SELECT * FROM workers WHERE id = 'wrk-1'").fetchone()
    result = worker_may_auto_attend_today(
        db_conn, worker, target_date=date(2026, 6, 10), now=__import__("datetime").datetime(2026, 6, 10, 18, 0)
    )
    assert result["ok"] is False
    assert result["reason"] == "outside_work_hours"


def test_allows_inside_company_work_hours(db_conn):
    worker = db_conn.execute("SELECT * FROM workers WHERE id = 'wrk-1'").fetchone()
    result = worker_may_auto_attend_today(
        db_conn, worker, target_date=date(2026, 6, 10), now=__import__("datetime").datetime(2026, 6, 10, 9, 0)
    )
    assert result["ok"] is True
    assert result["dayType"] == "workday"
    assert result["shiftStart"] == "08:00"
    assert result["shiftEnd"] == "17:00"
