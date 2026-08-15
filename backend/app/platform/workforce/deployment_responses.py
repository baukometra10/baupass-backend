"""Worker responses to scheduled deployment days (decline / undo)."""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _business_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(os.getenv("BAUPASS_BUSINESS_TZ", "Europe/Berlin"))
        return datetime.now(tz)
    except Exception:
        return datetime.now(timezone.utc)


def _business_today() -> date:
    return _business_now().date()


def decline_cutoff_hours() -> float:
    """Hours before shift start when decline is locked. Default 2h."""
    raw = str(os.getenv("BAUPASS_DEPLOYMENT_DECLINE_CUTOFF_HOURS", "2")).strip()
    try:
        hours = float(raw)
    except ValueError:
        hours = 2.0
    return max(0.25, min(48.0, hours))


def _parse_shift_start_hm(value: str) -> tuple[int, int] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    # Accept HH:MM or HH:MM:SS
    parts = raw.replace(".", ":").split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError, IndexError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def worker_checked_in_on_date(db, *, worker_id: str, work_date: date) -> bool:
    """True if worker has a check-in / app-login access log on that calendar day."""
    day = work_date.isoformat()
    try:
        row = db.execute(
            """
            SELECT id FROM access_logs
            WHERE worker_id = ?
              AND direction IN ('check-in', 'app-login')
              AND substr(timestamp, 1, 10) = ?
            LIMIT 1
            """,
            (str(worker_id), day),
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def evaluate_decline_allowed(
    db,
    *,
    worker_id: str,
    work_date: date,
    shift_start: str = "",
) -> tuple[bool, str, dict[str, Any]]:
    """
    Returns (allowed, block_reason, meta).
    block_reason: '' | past_day | checked_in | cutoff
    """
    today = _business_today()
    meta: dict[str, Any] = {
        "cutoffHours": decline_cutoff_hours(),
        "shiftStart": str(shift_start or "").strip()[:16],
    }
    if work_date < today:
        return False, "past_day", meta
    if worker_checked_in_on_date(db, worker_id=str(worker_id), work_date=work_date):
        return False, "checked_in", meta

    hm = _parse_shift_start_hm(shift_start)
    if hm is None:
        # No explicit start — lock from midnight of that day (safer than open-ended).
        hm = (0, 0)
    hour, minute = hm
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(os.getenv("BAUPASS_BUSINESS_TZ", "Europe/Berlin"))
        start_dt = datetime(work_date.year, work_date.month, work_date.day, hour, minute, tzinfo=tz)
        now = datetime.now(tz)
    except Exception:
        start_dt = datetime(work_date.year, work_date.month, work_date.day, hour, minute, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

    cutoff = decline_cutoff_hours()
    lock_from = start_dt.timestamp() - (cutoff * 3600.0)
    meta["shiftStartAt"] = start_dt.isoformat()
    meta["lockFrom"] = datetime.fromtimestamp(lock_from, tz=start_dt.tzinfo).isoformat()
    if now.timestamp() >= lock_from:
        return False, "cutoff", meta
    return True, "", meta


def enrich_days_with_decline_rules(
    db,
    *,
    worker_id: str,
    days: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach canDecline / declineBlockReason for worker UI."""
    from .attendance_eligibility import is_real_deployment_location

    out: list[dict[str, Any]] = []
    for day in days:
        item = dict(day)
        iso = str(item.get("date") or "")[:10]
        parsed = _parse_work_date(iso)
        declined = str(item.get("workerResponse") or "").lower() == "declined" or item.get("isDeclined") is True
        loc = str(item.get("location") or "").strip()
        has_assignment = is_real_deployment_location(loc)
        if not has_assignment or declined or not parsed:
            item["canDecline"] = False
            item["canSwap"] = bool(has_assignment) and not declined and parsed is not None and parsed >= _business_today()
            item["declineBlockReason"] = (
                "not_applicable" if not has_assignment else ("declined" if declined else "")
            )
            out.append(item)
            continue
        allowed, reason, meta = evaluate_decline_allowed(
            db,
            worker_id=str(worker_id),
            work_date=parsed,
            shift_start=str(item.get("shiftStart") or item.get("shift_start") or ""),
        )
        item["canDecline"] = bool(allowed)
        item["canSwap"] = parsed >= _business_today()
        item["declineBlockReason"] = reason
        item["declineCutoffHours"] = meta.get("cutoffHours")
        if meta.get("lockFrom"):
            item["declineLockFrom"] = meta["lockFrom"]
        out.append(item)
    return out


def _ensure_admin_ack_columns(db) -> None:
    try:
        cols = {str(r[1]) for r in db.execute("PRAGMA table_info(worker_deployment_day_responses)").fetchall()}
    except Exception:
        return
    if "admin_acknowledged_at" not in cols:
        try:
            db.execute(
                "ALTER TABLE worker_deployment_day_responses ADD COLUMN admin_acknowledged_at TEXT"
            )
        except Exception:
            pass
    if "admin_acknowledged_by" not in cols:
        try:
            db.execute(
                "ALTER TABLE worker_deployment_day_responses ADD COLUMN admin_acknowledged_by TEXT"
            )
        except Exception:
            pass


def ensure_worker_deployment_day_responses_table(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS worker_deployment_day_responses (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            worker_id TEXT NOT NULL,
            work_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'declined',
            reason TEXT NOT NULL DEFAULT '',
            responded_at TEXT NOT NULL,
            admin_acknowledged_at TEXT,
            admin_acknowledged_by TEXT,
            UNIQUE(company_id, worker_id, work_date)
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wddr_company_worker_date
        ON worker_deployment_day_responses(company_id, worker_id, work_date)
        """
    )
    _ensure_admin_ack_columns(db)


def list_responses_for_month(
    db,
    *,
    company_id: str,
    worker_id: str,
    year: int,
    month: int,
) -> dict[str, dict[str, Any]]:
    from .deployment_store import month_bounds

    start, end = month_bounds(year, month)
    try:
        rows = db.execute(
            """
            SELECT work_date, status, reason, responded_at
            FROM worker_deployment_day_responses
            WHERE company_id = ? AND worker_id = ? AND work_date >= ? AND work_date <= ?
            """,
            (str(company_id), str(worker_id), start, end),
        ).fetchall()
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row["work_date"])
        out[key] = {
            "workerResponse": str(row["status"] or ""),
            "declineReason": str(row["reason"] or ""),
            "respondedAt": row["responded_at"],
        }
    return out


def attach_responses_to_days(days: list[dict[str, Any]], responses: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    for day in days:
        key = str(day.get("date") or "")
        extra = responses.get(key) or {}
        day["workerResponse"] = str(extra.get("workerResponse") or "")
        day["declineReason"] = str(extra.get("declineReason") or "")
        day["respondedAt"] = extra.get("respondedAt") or ""
        day["isDeclined"] = day["workerResponse"] == "declined"
    return days


def count_declined_days(days: list[dict[str, Any]]) -> int:
    return sum(1 for d in days if d.get("isDeclined") or d.get("workerResponse") == "declined")


def list_company_declines_for_month(
    db,
    *,
    company_id: str,
    year: int,
    month: int,
    limit: int = 30,
    unacknowledged_only: bool = True,
) -> list[dict[str, Any]]:
    from .deployment_store import month_bounds

    ensure_worker_deployment_day_responses_table(db)
    start, end = month_bounds(year, month)
    ack_filter = (
        "AND (r.admin_acknowledged_at IS NULL OR r.admin_acknowledged_at = '')"
        if unacknowledged_only
        else ""
    )
    try:
        rows = db.execute(
            f"""
            SELECT r.work_date, r.reason, r.responded_at,
                   w.id AS worker_id, w.first_name, w.last_name, w.badge_id,
                   d.location_label
            FROM worker_deployment_day_responses r
            JOIN workers w ON w.id = r.worker_id AND w.company_id = r.company_id
            LEFT JOIN worker_deployment_days d
              ON d.company_id = r.company_id AND d.worker_id = r.worker_id
             AND d.work_date = r.work_date
            WHERE r.company_id = ? AND r.status = 'declined'
              AND r.work_date >= ? AND r.work_date <= ?
              {ack_filter}
            ORDER BY r.responded_at DESC
            LIMIT ?
            """,
            (str(company_id), start, end, int(limit)),
        ).fetchall()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "workerId": str(row["worker_id"]),
                "workerName": f"{row['first_name']} {row['last_name']}".strip(),
                "badgeId": row["badge_id"],
                "workDate": str(row["work_date"]),
                "location": str(row["location_label"] or "").strip(),
                "reason": str(row["reason"] or "").strip(),
                "respondedAt": row["responded_at"],
            }
        )
    return out


def count_unacknowledged_declines_for_month(
    db,
    *,
    company_id: str,
    year: int,
    month: int,
) -> int:
    from .deployment_store import month_bounds

    ensure_worker_deployment_day_responses_table(db)
    start, end = month_bounds(year, month)
    try:
        row = db.execute(
            """
            SELECT COUNT(*) AS c
            FROM worker_deployment_day_responses
            WHERE company_id = ? AND status = 'declined'
              AND work_date >= ? AND work_date <= ?
              AND (admin_acknowledged_at IS NULL OR admin_acknowledged_at = '')
            """,
            (str(company_id), start, end),
        ).fetchone()
        return int(row["c"] or 0) if row else 0
    except Exception:
        return 0


def _resolve_deployment_decline_alerts(
    db,
    *,
    company_id: str,
    worker_id: str,
    work_date: str,
) -> None:
    try:
        rows = db.execute(
            """
            SELECT id, details FROM system_alerts
            WHERE code = 'deployment_worker_declined' AND resolved_at IS NULL
            ORDER BY created_at DESC
            LIMIT 80
            """
        ).fetchall()
    except Exception:
        return
    work_iso = str(work_date)[:10]
    now = _now_iso()
    for row in rows:
        try:
            details = json.loads(str(row["details"] or "{}"))
        except Exception:
            continue
        if str(details.get("companyId") or "") != str(company_id):
            continue
        if str(details.get("workerId") or "") != str(worker_id):
            continue
        if str(details.get("workDate") or "")[:10] != work_iso:
            continue
        try:
            db.execute(
                "UPDATE system_alerts SET resolved_at = ? WHERE id = ?",
                (now, row["id"]),
            )
        except Exception:
            pass


def acknowledge_deployment_decline(
    db,
    *,
    company_id: str,
    worker_id: str,
    work_date: str,
    user_id: str,
) -> tuple[dict[str, Any] | None, tuple[Any, int] | None]:
    ensure_worker_deployment_day_responses_table(db)
    parsed = _parse_work_date(work_date)
    if not parsed:
        return None, ({"error": "invalid_date"}, 400)
    work_iso = parsed.isoformat()
    row = db.execute(
        """
        SELECT id, status FROM worker_deployment_day_responses
        WHERE company_id = ? AND worker_id = ? AND work_date = ?
        """,
        (str(company_id), str(worker_id), work_iso),
    ).fetchone()
    if not row or str(row["status"] or "") != "declined":
        return None, ({"error": "decline_not_found"}, 404)
    now = _now_iso()
    db.execute(
        """
        UPDATE worker_deployment_day_responses
        SET admin_acknowledged_at = ?, admin_acknowledged_by = ?
        WHERE company_id = ? AND worker_id = ? AND work_date = ?
        """,
        (now, str(user_id or ""), str(company_id), str(worker_id), work_iso),
    )
    _resolve_deployment_decline_alerts(
        db,
        company_id=str(company_id),
        worker_id=str(worker_id),
        work_date=work_iso,
    )
    db.commit()
    try:
        from backend.app.platform.inbox.events import notify_inbox_changed

        notify_inbox_changed(str(company_id), source="deployment_decline_ack")
    except Exception:
        pass
    return {
        "ok": True,
        "workerId": str(worker_id),
        "workDate": work_iso,
        "acknowledgedAt": now,
    }, None


def clear_worker_declines_for_month(
    db,
    *,
    company_id: str,
    worker_id: str,
    year: int,
    month: int,
) -> int:
    from .deployment_store import month_bounds

    ensure_worker_deployment_day_responses_table(db)
    start, end = month_bounds(year, month)
    try:
        cur = db.execute(
            """
            DELETE FROM worker_deployment_day_responses
            WHERE company_id = ? AND worker_id = ? AND work_date >= ? AND work_date <= ?
            """,
            (str(company_id), str(worker_id), start, end),
        )
        db.commit()
        return int(cur.rowcount or 0)
    except Exception:
        return 0


def _parse_work_date(work_date: str) -> date | None:
    raw = str(work_date or "").strip()[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def set_worker_day_response(
    db,
    *,
    company_id: str,
    worker_id: str,
    work_date: str,
    action: str,
    reason: str = "",
) -> tuple[dict[str, Any] | None, tuple[Any, int] | None]:
    """
    action: decline | undo
    Returns (payload, error_response) where error_response is (flask_response, status).
    """
    from .deployment_store import build_month_calendar, list_deployment_days
    from .deployment_worker import worker_can_respond_to_deployment_month

    ensure_worker_deployment_day_responses_table(db)

    parsed = _parse_work_date(work_date)
    if not parsed:
        return None, ({"error": "invalid_date"}, 400)

    year, month = parsed.year, parsed.month
    if not worker_can_respond_to_deployment_month(
        db,
        company_id=str(company_id),
        worker_id=str(worker_id),
        year=year,
        month=month,
    ):
        return None, ({"error": "plan_not_published"}, 403)

    today = _business_today()
    if parsed < today:
        return None, ({"error": "past_day_not_allowed"}, 400)

    work_iso = parsed.isoformat()
    stored = list_deployment_days(
        db, company_id=str(company_id), worker_id=str(worker_id), year=year, month=month
    )
    day_row = next((r for r in stored if str(r.get("work_date") or "")[:10] == work_iso), None)
    location = str(day_row.get("location_label") or "").strip() if day_row else ""
    if not location:
        calendar_days = build_month_calendar(
            db,
            company_id=str(company_id),
            worker_id=str(worker_id),
            year=year,
            month=month,
        )
        cal_day = next((d for d in calendar_days if str(d.get("date") or "")[:10] == work_iso), None)
        location = str((cal_day or {}).get("location") or "").strip()
    if not location:
        return None, ({"error": "no_assignment_for_day"}, 400)

    action_norm = str(action or "").strip().lower()
    if action_norm == "undo":
        db.execute(
            """
            DELETE FROM worker_deployment_day_responses
            WHERE company_id = ? AND worker_id = ? AND work_date = ?
            """,
            (str(company_id), str(worker_id), parsed.isoformat()),
        )
        db.commit()
        return {
            "ok": True,
            "date": parsed.isoformat(),
            "workerResponse": "",
            "declineReason": "",
        }, None

    if action_norm != "decline":
        return None, ({"error": "invalid_action"}, 400)

    shift_start = ""
    if day_row:
        shift_start = str(day_row.get("shift_start") or "")[:16]
    if not shift_start:
        calendar_days = build_month_calendar(
            db,
            company_id=str(company_id),
            worker_id=str(worker_id),
            year=year,
            month=month,
        )
        cal_day = next((d for d in calendar_days if str(d.get("date") or "")[:10] == work_iso), None)
        shift_start = str((cal_day or {}).get("shiftStart") or "")[:16]

    allowed, block_reason, meta = evaluate_decline_allowed(
        db,
        worker_id=str(worker_id),
        work_date=parsed,
        shift_start=shift_start,
    )
    if not allowed:
        error_code = {
            "past_day": "past_day_not_allowed",
            "checked_in": "deployment_decline_after_checkin",
            "cutoff": "deployment_decline_cutoff_elapsed",
        }.get(block_reason, "deployment_decline_blocked")
        message = {
            "past_day": "Vergangene Tage können nicht abgelehnt werden.",
            "checked_in": "Nach dem Check-in kann dieser Tag nicht mehr abgelehnt werden.",
            "cutoff": (
                f"Ablehnen ist nur bis {meta.get('cutoffHours', 2)} Stunden vor Schichtbeginn möglich."
            ),
        }.get(block_reason, "Ablehnen nicht möglich.")
        return None, (
            {
                "error": error_code,
                "message": message,
                "blockReason": block_reason,
                "cutoffHours": meta.get("cutoffHours"),
                "shiftStart": meta.get("shiftStart"),
                "lockFrom": meta.get("lockFrom"),
            },
            409,
        )

    reason_clean = str(reason or "").strip()[:500]
    row_id = f"wdr-{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    try:
        db.execute(
            """
            INSERT INTO worker_deployment_day_responses
                (id, company_id, worker_id, work_date, status, reason, responded_at)
            VALUES (?, ?, ?, ?, 'declined', ?, ?)
            ON CONFLICT(company_id, worker_id, work_date) DO UPDATE SET
                status = 'declined',
                reason = excluded.reason,
                responded_at = excluded.responded_at
            """,
            (row_id, str(company_id), str(worker_id), work_iso, reason_clean, now),
        )
        db.commit()
    except Exception as exc:
        return None, ({"error": "decline_save_failed", "message": str(exc)[:200]}, 500)

    return {
        "ok": True,
        "date": parsed.isoformat(),
        "workerResponse": "declined",
        "declineReason": reason_clean,
        "respondedAt": now,
    }, None


def ensure_shift_assignment_for_work_date(db, *, worker, work_date: str) -> str | None:
    """
    Find or create a shift_assignments row for a deployment work day so swap can reuse
    the existing shift-swap APIs.
    """
    import secrets
    from .deployment_store import build_month_calendar, list_deployment_days

    parsed = _parse_work_date(work_date)
    if not parsed:
        return None
    wid = str(worker["id"])
    cid = str(worker["company_id"])
    day = parsed.isoformat()

    try:
        existing = db.execute(
            """
            SELECT id FROM shift_assignments
            WHERE worker_id = ? AND company_id = ? AND status != 'cancelled'
              AND substr(replace(coalesce(start_time, ''), 'T', ' '), 1, 10) = ?
            ORDER BY start_time ASC
            LIMIT 1
            """,
            (wid, cid, day),
        ).fetchone()
        if existing:
            return str(existing["id"])
    except Exception:
        existing = None

    stored = list_deployment_days(
        db, company_id=cid, worker_id=wid, year=parsed.year, month=parsed.month
    )
    day_row = next((r for r in stored if str(r.get("work_date") or "")[:10] == day), None)
    location = str((day_row or {}).get("location_label") or "").strip()
    shift_start = str((day_row or {}).get("shift_start") or "").strip()[:16]
    shift_end = str((day_row or {}).get("shift_end") or "").strip()[:16]
    if not location:
        cal = build_month_calendar(
            db, company_id=cid, worker_id=wid, year=parsed.year, month=parsed.month
        )
        cal_day = next((d for d in cal if str(d.get("date") or "")[:10] == day), None)
        location = str((cal_day or {}).get("location") or "").strip()
        shift_start = shift_start or str((cal_day or {}).get("shiftStart") or "").strip()[:16]
        shift_end = shift_end or str((cal_day or {}).get("shiftEnd") or "").strip()[:16]

    from .attendance_eligibility import is_real_deployment_location

    if not is_real_deployment_location(location):
        return None

    hm_start = _parse_shift_start_hm(shift_start) or (7, 0)
    hm_end = _parse_shift_start_hm(shift_end) or (16, 0)
    start_iso = f"{day}T{hm_start[0]:02d}:{hm_start[1]:02d}:00"
    end_iso = f"{day}T{hm_end[0]:02d}:{hm_end[1]:02d}:00"
    assignment_id = f"sa-{secrets.token_hex(8)}"
    try:
        from backend.server import now_iso

        stamp = now_iso()
    except Exception:
        stamp = _now_iso()
    try:
        db.execute(
            """
            INSERT INTO shift_assignments (
                id, company_id, site, worker_id, assigned_at, start_time, end_time,
                status, notes, created_by_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'assigned', ?, ?)
            """,
            (
                assignment_id,
                cid,
                location[:120],
                wid,
                stamp,
                start_iso,
                end_iso,
                f"deployment:{day}",
                None,
            ),
        )
        db.commit()
        return assignment_id
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None
