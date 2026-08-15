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


# Significant move for live-map pin updates (~1 m).
LIVE_LOCATION_MIN_MOVE_METERS = 1.0

_LIVE_LOCATION_COLUMNS_READY = False


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math

    earth = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlng / 2) ** 2
    return 2 * earth * math.asin(math.sqrt(min(1.0, a)))


def _row_get(row: Any, key: str, default=None):
    if row is None:
        return default
    try:
        return row[key]
    except Exception:
        try:
            return row[key.lower()]
        except Exception:
            return default


def _safe_rollback(db) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def ensure_live_location_columns(db) -> str:
    """
    Make sure worker_presence_state can store live GPS.
    Safe to call repeatedly. Returns empty string on success, else a short error.
    """
    global _LIVE_LOCATION_COLUMNS_READY
    if _LIVE_LOCATION_COLUMNS_READY:
        return ""
    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_presence_state (
                worker_id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL DEFAULT '',
                open_direction TEXT NOT NULL DEFAULT '',
                last_checkin_at TEXT NOT NULL DEFAULT '',
                last_checkout_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                last_lat REAL,
                last_lng REAL,
                last_accuracy_m REAL,
                last_location_at TEXT DEFAULT ''
            )
            """
        )
    except Exception as exc:
        _safe_rollback(db)
        return f"create_table:{type(exc).__name__}"

    alters = (
        "ALTER TABLE worker_presence_state ADD COLUMN IF NOT EXISTS last_lat REAL",
        "ALTER TABLE worker_presence_state ADD COLUMN IF NOT EXISTS last_lng REAL",
        "ALTER TABLE worker_presence_state ADD COLUMN IF NOT EXISTS last_accuracy_m REAL",
        "ALTER TABLE worker_presence_state ADD COLUMN IF NOT EXISTS last_location_at TEXT DEFAULT ''",
    )
    for stmt in alters:
        try:
            db.execute(stmt)
        except Exception:
            _safe_rollback(db)
            # Older SQLite without IF NOT EXISTS — try plain ADD once.
            try:
                plain = stmt.replace(" IF NOT EXISTS", "")
                db.execute(plain)
            except Exception:
                _safe_rollback(db)
    try:
        db.commit()
    except Exception:
        pass
    # Verify columns are readable.
    try:
        db.execute(
            "SELECT last_lat, last_lng, last_accuracy_m, last_location_at "
            "FROM worker_presence_state LIMIT 0"
        )
        _LIVE_LOCATION_COLUMNS_READY = True
        return ""
    except Exception as exc:
        _safe_rollback(db)
        return f"verify_cols:{type(exc).__name__}:{exc}"


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
    ok, _reason = upsert_live_location_ex(
        db,
        worker_id=worker_id,
        company_id=company_id,
        lat=lat,
        lng=lng,
        accuracy_m=accuracy_m,
        at=at,
        min_move_meters=min_move_meters,
    )
    return ok


def upsert_live_location_ex(
    db,
    *,
    worker_id: str,
    company_id: str,
    lat: float,
    lng: float,
    accuracy_m: float | None = None,
    at: str | None = None,
    min_move_meters: float = LIVE_LOCATION_MIN_MOVE_METERS,
) -> tuple[bool, str]:
    """
    Persist latest device GPS for live ops map.

    Always refreshes last_location_at. Coordinates update when moved ≥ min_move_meters.
    Returns (ok, reason) where reason is empty on success.
    """
    import logging

    log = logging.getLogger("baupass.presence")
    try:
        la = float(lat)
        ln = float(lng)
    except (TypeError, ValueError):
        return False, "invalid_lat_lng"
    if not (-90.0 <= la <= 90.0 and -180.0 <= ln <= 180.0):
        return False, "out_of_range"
    if abs(la) < 0.0001 and abs(ln) < 0.0001:
        return False, "null_island"
    stamp = str(at or "").strip() or _now_iso()
    acc = None
    if accuracy_m is not None:
        try:
            acc = float(accuracy_m)
        except (TypeError, ValueError):
            acc = None
    wid = str(worker_id or "").strip()
    cid = str(company_id or "").strip()
    if not wid:
        return False, "missing_worker_id"
    if not cid:
        return False, "missing_company_id"

    schema_err = ensure_live_location_columns(db)
    if schema_err:
        log.warning("live location schema: %s", schema_err)
        # Continue — columns may already exist even if verify failed on empty table.

    # Existence check must NOT reference last_lat (works on old schemas).
    try:
        existing = db.execute(
            "SELECT worker_id FROM worker_presence_state WHERE worker_id = ? LIMIT 1",
            (wid,),
        ).fetchone()
    except Exception as exc:
        _safe_rollback(db)
        log.warning("presence select failed worker=%s: %s", wid, exc)
        return False, f"select:{type(exc).__name__}"

    moved = True
    prev_lat = prev_lng = None
    if existing is not None:
        try:
            prev = db.execute(
                "SELECT last_lat, last_lng FROM worker_presence_state WHERE worker_id = ? LIMIT 1",
                (wid,),
            ).fetchone()
            prev_lat = _row_get(prev, "last_lat")
            prev_lng = _row_get(prev, "last_lng")
            if prev_lat is not None and prev_lng is not None:
                dist = _haversine_meters(float(prev_lat), float(prev_lng), la, ln)
                moved = dist >= float(min_move_meters)
        except Exception:
            _safe_rollback(db)
            moved = True

    try:
        if existing is not None:
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
                # Heartbeat — do not use COALESCE (can fail on some PG adapters).
                if acc is None:
                    db.execute(
                        """
                        UPDATE worker_presence_state
                        SET company_id = ?, last_location_at = ?, updated_at = ?
                        WHERE worker_id = ?
                        """,
                        (cid, stamp, stamp, wid),
                    )
                else:
                    db.execute(
                        """
                        UPDATE worker_presence_state
                        SET company_id = ?, last_accuracy_m = ?,
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
        return True, "moved" if moved else "heartbeat"
    except Exception as exc:
        _safe_rollback(db)
        log.warning("upsert_live_location write failed worker=%s: %s", wid, exc)
        # Absolute last resort: update coords only.
        try:
            db.execute(
                """
                UPDATE worker_presence_state
                SET last_lat = ?, last_lng = ?, last_location_at = ?, updated_at = ?
                WHERE worker_id = ?
                """,
                (la, ln, stamp, stamp, wid),
            )
            row = db.execute(
                "SELECT worker_id FROM worker_presence_state WHERE worker_id = ? LIMIT 1",
                (wid,),
            ).fetchone()
            if row is not None:
                return True, "fallback_update"
            db.execute(
                """
                INSERT INTO worker_presence_state (
                    worker_id, company_id, open_direction,
                    last_checkin_at, last_checkout_at, updated_at,
                    last_lat, last_lng, last_location_at
                ) VALUES (?, ?, '', '', '', ?, ?, ?, ?)
                """,
                (wid, cid, stamp, la, ln, stamp),
            )
            return True, "fallback_insert"
        except Exception as exc2:
            _safe_rollback(db)
            log.warning("upsert_live_location fallback failed worker=%s: %s", wid, exc2)
            return False, f"write:{type(exc2).__name__}:{exc2}"


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
