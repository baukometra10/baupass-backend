"""Upcoming shifts merge deployment plan days into Meine Schichten."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from backend.app.platform.workforce.deployment_responses import (
    list_upcoming_worker_shift_assignments,
)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE shift_assignments (
            id TEXT PRIMARY KEY,
            company_id TEXT,
            worker_id TEXT,
            start_time TEXT,
            end_time TEXT,
            site TEXT,
            status TEXT,
            notes TEXT
        );
        CREATE TABLE worker_deployment_days (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            worker_id TEXT NOT NULL,
            work_date TEXT NOT NULL,
            location_label TEXT NOT NULL,
            shift_start TEXT NOT NULL DEFAULT '',
            shift_end TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            day_color TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'manual',
            updated_at TEXT NOT NULL,
            swap_status TEXT NOT NULL DEFAULT '',
            swap_partner_id TEXT NOT NULL DEFAULT '',
            swap_partner_name TEXT NOT NULL DEFAULT '',
            swap_id TEXT NOT NULL DEFAULT '',
            UNIQUE(company_id, worker_id, work_date)
        );
        CREATE TABLE worker_deployment_day_responses (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            worker_id TEXT NOT NULL,
            work_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'declined',
            reason TEXT NOT NULL DEFAULT '',
            responded_at TEXT NOT NULL,
            UNIQUE(company_id, worker_id, work_date)
        );
        """
    )
    return conn


def test_upcoming_includes_deployment_day_without_shift_row(monkeypatch):
    db = _db()
    day = (date.today() + timedelta(days=3)).isoformat()
    db.execute(
        """
        INSERT INTO worker_deployment_days
            (id, company_id, worker_id, work_date, location_label, shift_start, shift_end, source, updated_at)
        VALUES ('d1','c1','w1',?,'Baustelle A','07:00','16:00','manual','2026-01-01T00:00:00Z')
        """,
        (day,),
    )
    db.commit()

    import backend.app.platform.workforce.deployment_responses as mod

    monkeypatch.setattr(mod, "_business_today", lambda: date.today())

    rows = list_upcoming_worker_shift_assignments(db, worker_id="w1", company_id="c1")
    assert any(r.get("workDate") == day and r.get("source") == "deployment" for r in rows)
    match = next(r for r in rows if r.get("workDate") == day)
    assert match["site"] == "Baustelle A"
    assert match["id"] == ""


def test_upcoming_skips_declined_and_swapped_out(monkeypatch):
    db = _db()
    day_declined = (date.today() + timedelta(days=4)).isoformat()
    day_swapped = (date.today() + timedelta(days=5)).isoformat()
    db.execute(
        """
        INSERT INTO worker_deployment_days
            (id, company_id, worker_id, work_date, location_label, shift_start, shift_end, source, updated_at, swap_status)
        VALUES
            ('d2','c1','w1',?,'Site B','08:00','17:00','manual','2026-01-01T00:00:00Z',''),
            ('d3','c1','w1',?,'Site C','08:00','17:00','manual','2026-01-01T00:00:00Z','out')
        """,
        (day_declined, day_swapped),
    )
    db.execute(
        """
        INSERT INTO worker_deployment_day_responses
            (id, company_id, worker_id, work_date, status, reason, responded_at)
        VALUES ('r1','c1','w1',?,'declined','','2026-01-01T00:00:00Z')
        """,
        (day_declined,),
    )
    db.commit()

    import backend.app.platform.workforce.deployment_responses as mod

    monkeypatch.setattr(mod, "_business_today", lambda: date.today())
    rows = list_upcoming_worker_shift_assignments(db, worker_id="w1", company_id="c1")
    dates = {r.get("workDate") for r in rows}
    assert day_declined not in dates
    assert day_swapped not in dates
