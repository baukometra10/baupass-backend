"""Cached open check-in / check-out state for fast gate auto-toggle."""
from __future__ import annotations

from typing import Any


def get_presence_open_direction(db, worker_id: str) -> str:
    """Return 'check-in' if worker currently has an open session, else ''."""
    try:
        row = db.execute(
            """
            SELECT open_direction FROM worker_presence_state
            WHERE worker_id = ?
            LIMIT 1
            """,
            (str(worker_id),),
        ).fetchone()
        if row:
            direction = str(row["open_direction"] or "").strip().lower()
            if direction == "check-in":
                return "check-in"
            return ""
    except Exception:
        pass
    # Fallback: latest access log.
    try:
        latest = db.execute(
            """
            SELECT direction FROM access_logs
            WHERE worker_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            (str(worker_id),),
        ).fetchone()
        if latest and str(latest["direction"] or "").lower() == "check-in":
            return "check-in"
    except Exception:
        pass
    return ""


def upsert_presence_after_access(
    db,
    *,
    worker_id: str,
    company_id: str,
    direction: str,
    timestamp_iso: str,
) -> None:
    """Update presence row after a successful check-in or check-out."""
    direction_l = str(direction or "").strip().lower()
    if direction_l not in {"check-in", "check-out"}:
        return
    open_direction = "check-in" if direction_l == "check-in" else ""
    checkin_at = timestamp_iso if direction_l == "check-in" else ""
    checkout_at = timestamp_iso if direction_l == "check-out" else ""
    try:
        existing = db.execute(
            "SELECT worker_id, last_checkin_at, last_checkout_at FROM worker_presence_state WHERE worker_id = ?",
            (str(worker_id),),
        ).fetchone()
        if existing:
            keep_in = str(existing["last_checkin_at"] or "")
            keep_out = str(existing["last_checkout_at"] or "")
            if checkin_at:
                keep_in = checkin_at
            if checkout_at:
                keep_out = checkout_at
            db.execute(
                """
                UPDATE worker_presence_state
                SET company_id = ?, open_direction = ?, last_checkin_at = ?,
                    last_checkout_at = ?, updated_at = ?
                WHERE worker_id = ?
                """,
                (
                    str(company_id),
                    open_direction,
                    keep_in,
                    keep_out,
                    timestamp_iso,
                    str(worker_id),
                ),
            )
        else:
            db.execute(
                """
                INSERT INTO worker_presence_state (
                    worker_id, company_id, open_direction,
                    last_checkin_at, last_checkout_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(worker_id),
                    str(company_id),
                    open_direction,
                    checkin_at,
                    checkout_at,
                    timestamp_iso,
                ),
            )
    except Exception:
        # Table may not exist yet on very old DBs; ignore.
        pass


def resolve_auto_direction(db, worker_id: str) -> str:
    """Next tap direction when client asks for auto/toggle."""
    open_dir = get_presence_open_direction(db, worker_id)
    return "check-out" if open_dir == "check-in" else "check-in"
