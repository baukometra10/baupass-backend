"""Accepted swap moves deployment day to Y and marks X as swapped-out."""
from __future__ import annotations

import sqlite3

from backend.app.platform.workforce.deployment_responses import (
    apply_accepted_shift_swap_to_deployment,
    ensure_deployment_swap_columns,
    transfer_deployment_day_for_swap,
)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE workers (
            id TEXT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            company_id TEXT
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
    ensure_deployment_swap_columns(conn)
    conn.execute(
        "INSERT INTO workers (id, first_name, last_name, company_id) VALUES ('wx','Max','Mustermann','c1')"
    )
    conn.execute(
        "INSERT INTO workers (id, first_name, last_name, company_id) VALUES ('wy','Yuri','Schmidt','c1')"
    )
    conn.execute(
        """
        INSERT INTO worker_deployment_days
            (id, company_id, worker_id, work_date, location_label, shift_start, shift_end, notes, source, updated_at)
        VALUES ('d1','c1','wx','2026-08-25','Baustelle Nord','07:00','16:00','','manual','2026-01-01T00:00:00Z')
        """
    )
    conn.commit()
    return conn


def test_transfer_marks_x_out_and_gives_y_the_day():
    db = _db()
    ok = transfer_deployment_day_for_swap(
        db,
        company_id="c1",
        from_worker_id="wx",
        to_worker_id="wy",
        work_date="2026-08-25",
        swap_id="swap-1",
    )
    assert ok is True
    x = db.execute(
        "SELECT * FROM worker_deployment_days WHERE worker_id='wx' AND work_date='2026-08-25'"
    ).fetchone()
    y = db.execute(
        "SELECT * FROM worker_deployment_days WHERE worker_id='wy' AND work_date='2026-08-25'"
    ).fetchone()
    assert x["swap_status"] == "out"
    assert x["swap_partner_name"] == "Yuri Schmidt"
    assert x["location_label"] == "Baustelle Nord"
    assert y["location_label"] == "Baustelle Nord"
    assert y["shift_start"] == "07:00"
    assert y["swap_status"] == "in"
    assert y["swap_partner_name"] == "Max Mustermann"


def test_apply_accepted_uses_assignment_start():
    db = _db()
    result = apply_accepted_shift_swap_to_deployment(
        db,
        company_id="c1",
        from_worker_id="wx",
        to_worker_id="wy",
        assignment_start="2026-08-25T07:00:00",
        swap_id="swap-2",
    )
    assert result["deploymentTransferred"] is True
    assert result["workDate"] == "2026-08-25"
