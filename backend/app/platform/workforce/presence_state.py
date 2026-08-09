"""Cached open check-in / check-out state for fast gate auto-toggle."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


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
    clear_live = direction_l == "check-out"
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
            if clear_live:
                try:
                    db.execute(
                        """
                        UPDATE worker_presence_state
                        SET company_id = ?, open_direction = ?, last_checkin_at = ?,
                            last_checkout_at = ?, updated_at = ?,
                            last_lat = NULL, last_lng = NULL, last_accuracy_m = NULL,
                            last_location_at = '',
                            activity = 'working', activity_note = '', activity_updated_at = ?,
                            task_ref = ''
                        WHERE worker_id = ?
                        """,
                        (
                            str(company_id),
                            open_direction,
                            keep_in,
                            keep_out,
                            timestamp_iso,
                            timestamp_iso,
                            str(worker_id),
                        ),
                    )
                except Exception:
                    db.execute(
                        """
                        UPDATE worker_presence_state
                        SET company_id = ?, open_direction = ?, last_checkin_at = ?,
                            last_checkout_at = ?, updated_at = ?,
                            last_lat = NULL, last_lng = NULL, last_accuracy_m = NULL,
                            last_location_at = ''
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


# Significant move for live-map pin updates (~1 m so employers see near-realtime walking).
LIVE_LOCATION_MIN_MOVE_METERS = 1.0


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math

    earth = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlng / 2) ** 2
    return 2 * earth * math.asin(math.sqrt(min(1.0, a)))


def upsert_live_location(
    db,
    *,
    worker_id: str,
    company_id: str,
    lat: float,
    lng: float,
    accuracy_m: float | None = None,
    at: str | None = None,
    min_move_meters: float = LIVE_LOCATION_MIN_MOVE_METERS,
) -> bool:
    """
    Persist latest device GPS for live ops map.

    Always refreshes last_location_at (keeps pin "fresh"). Coordinates update when the
    worker moved ≥ min_move_meters (or on first fix) so tiny GPS jitter does not rewrite.
    """
    try:
        la = float(lat)
        ln = float(lng)
    except (TypeError, ValueError):
        return False
    if not (-90.0 <= la <= 90.0 and -180.0 <= ln <= 180.0):
        return False
    if abs(la) < 0.0001 and abs(ln) < 0.0001:
        return False
    stamp = str(at or "").strip() or _now_iso()
    acc = None
    if accuracy_m is not None:
        try:
            acc = float(accuracy_m)
        except (TypeError, ValueError):
            acc = None
    wid = str(worker_id)
    cid = str(company_id)
    try:
        existing = db.execute(
            """
            SELECT worker_id, last_lat, last_lng FROM worker_presence_state
            WHERE worker_id = ? LIMIT 1
            """,
            (wid,),
        ).fetchone()
        moved = True
        if existing is not None:
            try:
                prev_lat = existing["last_lat"]
                prev_lng = existing["last_lng"]
                if prev_lat is not None and prev_lng is not None:
                    dist = _haversine_meters(float(prev_lat), float(prev_lng), la, ln)
                    moved = dist >= float(min_move_meters)
            except (TypeError, ValueError):
                moved = True
            if moved:
                db.execute(
                    """
                    UPDATE worker_presence_state
                    SET company_id = ?, last_lat = ?, last_lng = ?, last_accuracy_m = ?,
                        last_location_at = ?, updated_at = ?
                    WHERE worker_id = ?
                    """,
                    (cid, la, ln, acc, stamp, stamp, wid),
                )
            else:
                # Heartbeat only — stay fresh on the map without jittering the pin.
                db.execute(
                    """
                    UPDATE worker_presence_state
                    SET company_id = ?, last_accuracy_m = COALESCE(?, last_accuracy_m),
                        last_location_at = ?, updated_at = ?
                    WHERE worker_id = ?
                    """,
                    (cid, acc, stamp, stamp, wid),
                )
        else:
            db.execute(
                """
                INSERT INTO worker_presence_state (
                    worker_id, company_id, open_direction,
                    last_checkin_at, last_checkout_at, updated_at,
                    last_lat, last_lng, last_accuracy_m, last_location_at
                ) VALUES (?, ?, '', '', '', ?, ?, ?, ?, ?)
                """,
                (wid, cid, stamp, la, ln, acc, stamp),
            )
        return True
    except Exception:
        return False


def resolve_auto_direction(db, worker_id: str) -> str:
    """Next tap direction when client asks for auto/toggle."""
    open_dir = get_presence_open_direction(db, worker_id)
    return "check-out" if open_dir == "check-in" else "check-in"


ACTIVITIES = frozenset({"working", "on_break", "on_task"})


def normalize_activity(value) -> str:
    act = str(value or "working").strip().lower()
    if act in {"break", "pause", "paused"}:
        return "on_break"
    if act in {"task", "mission", "job"}:
        return "on_task"
    return act if act in ACTIVITIES else "working"


def upsert_worker_activity(
    db,
    *,
    worker_id: str,
    company_id: str,
    activity: str,
    note: str = "",
    task_ref: str = "",
    at: str | None = None,
) -> bool:
    """Set operational activity (working / on_break / on_task) while on duty."""
    act = normalize_activity(activity)
    stamp = str(at or "").strip() or _now_iso()
    note_s = str(note or "").strip()[:240]
    task_s = str(task_ref or "").strip()[:120]
    wid = str(worker_id)
    cid = str(company_id)
    try:
        existing = db.execute(
            "SELECT worker_id FROM worker_presence_state WHERE worker_id = ? LIMIT 1",
            (wid,),
        ).fetchone()
        if existing:
            db.execute(
                """
                UPDATE worker_presence_state
                SET company_id = ?, activity = ?, activity_note = ?,
                    activity_updated_at = ?, task_ref = ?, updated_at = ?
                WHERE worker_id = ?
                """,
                (cid, act, note_s, stamp, task_s, stamp, wid),
            )
        else:
            db.execute(
                """
                INSERT INTO worker_presence_state (
                    worker_id, company_id, open_direction,
                    last_checkin_at, last_checkout_at, updated_at,
                    activity, activity_note, activity_updated_at, task_ref
                ) VALUES (?, ?, '', '', '', ?, ?, ?, ?, ?)
                """,
                (wid, cid, stamp, act, note_s, stamp, task_s),
            )
        return True
    except Exception:
        return False


def clear_worker_activity_on_checkout(db, *, worker_id: str, timestamp_iso: str) -> None:
    try:
        db.execute(
            """
            UPDATE worker_presence_state
            SET activity = 'working', activity_note = '', activity_updated_at = ?,
                task_ref = '', updated_at = ?
            WHERE worker_id = ?
            """,
            (timestamp_iso, timestamp_iso, str(worker_id)),
        )
    except Exception:
        pass
