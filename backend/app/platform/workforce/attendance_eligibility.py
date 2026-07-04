"""Rules for automatic attendance (proximity login, site auto check-in)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

_FREE_DEPLOYMENT_MARKERS = frozenset(
    {
        "frei",
        "free",
        "off",
        "aus",
        "-",
        "–",
        "—",
        "x",
        "urlaub",
        "free day",
        "kein einsatz",
        "no assignment",
        "off day",
    }
)

# Allow geofence check-in this many minutes before shift_start.
SHIFT_EARLY_MINUTES = 30


def is_real_deployment_location(location: str | None) -> bool:
    normalized = str(location or "").strip().lower()
    if not normalized:
        return False
    return normalized not in _FREE_DEPLOYMENT_MARKERS


def _parse_iso_date(value: str | None) -> date | None:
    raw = str(value or "").strip()[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _shift_hhmm(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "T" in raw and len(raw) >= 16:
        return raw[11:16]
    if ":" in raw:
        return raw[:5]
    return ""


def worker_on_approved_leave(db, worker_id: str, target_date: date | None = None) -> bool:
    """True when worker has approved leave covering target_date."""
    day = target_date or date.today()
    day_iso = day.isoformat()
    row = db.execute(
        """
        SELECT id FROM leave_requests
        WHERE worker_id = ?
          AND status = 'genehmigt'
          AND start_date <= ?
          AND end_date >= ?
        LIMIT 1
        """,
        (str(worker_id), day_iso, day_iso),
    ).fetchone()
    return bool(row)


def worker_deployment_day_row(
    db, *, company_id: str, worker_id: str, target_date: date
) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT work_date, location_label, shift_start, shift_end, notes, day_color
        FROM worker_deployment_days
        WHERE company_id = ? AND worker_id = ? AND work_date = ?
        LIMIT 1
        """,
        (str(company_id), str(worker_id), target_date.isoformat()),
    ).fetchone()
    return dict(row) if row else None


def worker_deployment_response_for_date(
    db, *, company_id: str, worker_id: str, target_date: date
) -> str:
    row = db.execute(
        """
        SELECT status FROM worker_deployment_day_responses
        WHERE company_id = ? AND worker_id = ? AND work_date = ?
        LIMIT 1
        """,
        (str(company_id), str(worker_id), target_date.isoformat()),
    ).fetchone()
    return str(row["status"] or "").strip().lower() if row else ""


def company_deployment_plan_active(db, company_id: str, year: int, month: int) -> bool:
    """True when the company uses Einsatzplan for attendance in this month."""
    from .deployment_store import month_bounds

    try:
        from .deployment_worker import month_plan_published

        if month_plan_published(db, str(company_id), int(year), int(month)):
            return True
    except Exception:
        pass
    start, end = month_bounds(year, month)
    row = db.execute(
        """
        SELECT 1 FROM worker_deployment_days
        WHERE company_id = ?
          AND work_date >= ? AND work_date <= ?
          AND TRIM(COALESCE(location_label, '')) != ''
        LIMIT 1
        """,
        (str(company_id), start, end),
    ).fetchone()
    return bool(row)


def worker_has_deployment_plan_usage(
    db, *, company_id: str, worker_id: str, year: int, month: int
) -> bool:
    from .deployment_store import month_bounds

    start, end = month_bounds(year, month)
    scheduled = db.execute(
        """
        SELECT location_label FROM worker_deployment_days
        WHERE company_id = ? AND worker_id = ?
          AND work_date >= ? AND work_date <= ?
          AND TRIM(COALESCE(location_label, '')) != ''
        """,
        (str(company_id), str(worker_id), start, end),
    ).fetchall()
    if any(is_real_deployment_location(str(row["location_label"] or "")) for row in scheduled):
        return True
    try:
        from .deployment_worker import month_plan_published

        if month_plan_published(db, company_id, year, month):
            return True
    except Exception:
        pass
    return False


def _effective_work_times(db, worker_id: str) -> tuple[str, str]:
    row = db.execute(
        """
        SELECT c.work_start_time AS company_work_start_time,
               c.work_end_time AS company_work_end_time,
               s.work_start_time AS global_work_start_time,
               s.work_end_time AS global_work_end_time
        FROM workers w
        LEFT JOIN companies c ON c.id = w.company_id
        LEFT JOIN settings s ON s.id = 1
        WHERE w.id = ?
        LIMIT 1
        """,
        (str(worker_id),),
    ).fetchone()
    if not row:
        return "", ""
    work_start = str(row["company_work_start_time"] or row["global_work_start_time"] or "").strip()
    work_end = str(row["company_work_end_time"] or row["global_work_end_time"] or "").strip()
    return work_start, work_end


def _shift_times(shift_start: str | None, shift_end: str | None) -> tuple[int, int] | None:
    start_raw = _shift_hhmm(shift_start)
    end_raw = _shift_hhmm(shift_end)
    if not start_raw or not end_raw:
        return None
    try:
        sh, sm = (int(x) for x in start_raw.split(":"))
        eh, em = (int(x) for x in end_raw.split(":"))
    except (TypeError, ValueError):
        return None
    return sh * 60 + sm, eh * 60 + em


def _within_shift_window(shift_start: str, shift_end: str, *, now: datetime | None = None) -> bool:
    parsed = _shift_times(shift_start, shift_end)
    if parsed is None:
        return False
    start_minutes, end_minutes = parsed
    current = now or datetime.now()
    current_minutes = current.hour * 60 + current.minute
    window_start = max(0, start_minutes - SHIFT_EARLY_MINUTES)
    # Night shift starting today (e.g. 22:00–06:00 on the same calendar day).
    if end_minutes < start_minutes:
        return current_minutes >= window_start or current_minutes <= end_minutes
    return window_start <= current_minutes <= end_minutes


def _overnight_morning_tail_active(shift_start: str, shift_end: str, *, now: datetime) -> bool:
    """True when now is in the morning tail of an overnight shift that started yesterday."""
    parsed = _shift_times(shift_start, shift_end)
    if parsed is None:
        return False
    start_minutes, end_minutes = parsed
    if end_minutes >= start_minutes:
        return False
    current_minutes = now.hour * 60 + now.minute
    return current_minutes <= end_minutes


def _deployment_row_context(row: dict[str, Any] | None) -> dict[str, str]:
    if not row:
        return {"location": "", "shiftStart": "", "shiftEnd": ""}
    return {
        "location": str(row.get("location_label") or "").strip(),
        "shiftStart": str(row.get("shift_start") or "").strip(),
        "shiftEnd": str(row.get("shift_end") or "").strip(),
    }


def _deployment_row_active_at(
    db,
    *,
    company_id: str,
    worker_id: str,
    work_date: date,
    row: dict[str, Any],
    now: datetime,
    overnight_tail_only: bool,
) -> bool:
    if worker_deployment_response_for_date(
        db, company_id=company_id, worker_id=worker_id, target_date=work_date
    ) == "declined":
        return False
    ctx = _deployment_row_context(row)
    if not is_real_deployment_location(ctx["location"]):
        return False
    if not ctx["shiftStart"] or not ctx["shiftEnd"]:
        return False
    if overnight_tail_only:
        return _overnight_morning_tail_active(ctx["shiftStart"], ctx["shiftEnd"], now=now)
    return _within_shift_window(ctx["shiftStart"], ctx["shiftEnd"], now=now)


def _resolve_active_deployment_at(
    db,
    *,
    company_id: str,
    worker_id: str,
    now: datetime,
) -> tuple[date | None, dict[str, Any] | None]:
    """Return (work_date, row) when an Einsatzplan shift window covers `now`."""
    today = now.date()
    yesterday = today - timedelta(days=1)

    today_row = worker_deployment_day_row(
        db, company_id=company_id, worker_id=worker_id, target_date=today
    )
    if today_row and _deployment_row_active_at(
        db,
        company_id=company_id,
        worker_id=worker_id,
        work_date=today,
        row=today_row,
        now=now,
        overnight_tail_only=False,
    ):
        return today, today_row

    yesterday_row = worker_deployment_day_row(
        db, company_id=company_id, worker_id=worker_id, target_date=yesterday
    )
    if yesterday_row and _deployment_row_active_at(
        db,
        company_id=company_id,
        worker_id=worker_id,
        work_date=yesterday,
        row=yesterday_row,
        now=now,
        overnight_tail_only=True,
    ):
        return yesterday, yesterday_row

    return None, None


def worker_may_auto_attend_today(
    db,
    worker: Any,
    *,
    target_date: date | None = None,
    now: datetime | None = None,
    lang: str = "de",
) -> dict[str, Any]:
    """
    Decide whether automatic attendance (proximity login / site auto check-in) is allowed.

    Returns {ok, reason, message, dayType, location, shiftStart, shiftEnd}.
    """
    from backend.server import is_company_workday_today, normalize_worker_type
    from backend.app.platform.sector.catalog import sector_attendance_message

    day = target_date or date.today()
    current = now or datetime.now()
    worker_id = str(worker["id"])
    company_id = str(worker["company_id"])

    if normalize_worker_type(worker["worker_type"]) != "worker":
        return {
            "ok": False,
            "reason": "visitor_not_eligible",
            "message": "Automatische Anmeldung gilt nur fuer Mitarbeiter.",
            "dayType": "visitor",
        }

    if worker_on_approved_leave(db, worker_id, day):
        return {
            "ok": False,
            "reason": "on_approved_leave",
            "message": sector_attendance_message(db, company_id, "attendanceOnLeave", lang=lang),
            "dayType": "leave",
        }

    response = worker_deployment_response_for_date(
        db, company_id=company_id, worker_id=worker_id, target_date=day
    )
    if response == "declined":
        return {
            "ok": False,
            "reason": "deployment_declined",
            "message": sector_attendance_message(db, company_id, "attendanceDeploymentDeclined", lang=lang),
            "dayType": "declined",
        }

    company_plan = company_deployment_plan_active(db, company_id, day.year, day.month)
    plan_active = company_plan or worker_has_deployment_plan_usage(
        db,
        company_id=company_id,
        worker_id=worker_id,
        year=day.year,
        month=day.month,
    )
    deployment_row = worker_deployment_day_row(
        db, company_id=company_id, worker_id=worker_id, target_date=day
    )
    ctx = _deployment_row_context(deployment_row)
    location = ctx["location"]
    shift_start = ctx["shiftStart"]
    shift_end = ctx["shiftEnd"]

    if plan_active:
        active_date, active_row = _resolve_active_deployment_at(
            db, company_id=company_id, worker_id=worker_id, now=current
        )
        if active_row:
            active_ctx = _deployment_row_context(active_row)
            return {
                "ok": True,
                "reason": "scheduled",
                "message": "",
                "dayType": "scheduled",
                "location": active_ctx["location"],
                "shiftStart": active_ctx["shiftStart"],
                "shiftEnd": active_ctx["shiftEnd"],
                "workDate": active_date.isoformat() if active_date else day.isoformat(),
            }

        if not is_real_deployment_location(location):
            return {
                "ok": False,
                "reason": "not_scheduled_today",
                "message": sector_attendance_message(db, company_id, "attendanceNotScheduledToday", lang=lang),
                "dayType": "free",
                "location": location or "",
                "shiftStart": shift_start,
                "shiftEnd": shift_end,
            }
        if not shift_start or not shift_end:
            return {
                "ok": False,
                "reason": "shift_times_required",
                "message": sector_attendance_message(db, company_id, "attendanceShiftTimesRequired", lang=lang),
                "dayType": "scheduled",
                "location": location,
                "shiftStart": shift_start,
                "shiftEnd": shift_end,
            }
        return {
            "ok": False,
            "reason": "outside_shift_window",
            "message": sector_attendance_message(db, company_id, "attendanceOutsideShift", lang=lang),
            "dayType": "scheduled",
            "location": location,
            "shiftStart": shift_start,
            "shiftEnd": shift_end,
        }

    # No deployment plan in use — fall back to standard workday (Mo–Fr) + company work hours.
    if day == date.today() and not is_company_workday_today():
        return {
            "ok": False,
            "reason": "not_a_workday",
            "message": sector_attendance_message(db, company_id, "attendanceNotWorkday", lang=lang),
            "dayType": "weekend",
        }
    if day.weekday() >= 5:
        return {
            "ok": False,
            "reason": "not_a_workday",
            "message": sector_attendance_message(db, company_id, "attendanceNotWorkday", lang=lang),
            "dayType": "weekend",
        }

    work_start, work_end = _effective_work_times(db, worker_id)
    if work_start and work_end:
        if not _within_shift_window(work_start, work_end, now=current):
            return {
                "ok": False,
                "reason": "outside_work_hours",
                "message": sector_attendance_message(db, company_id, "attendanceOutsideWorkHours", lang=lang),
                "dayType": "workday",
                "location": location,
                "shiftStart": work_start,
                "shiftEnd": work_end,
            }
        return {
            "ok": True,
            "reason": "workday",
            "message": "",
            "dayType": "workday",
            "location": location,
            "shiftStart": work_start,
            "shiftEnd": work_end,
        }

    return {
        "ok": True,
        "reason": "workday",
        "message": "",
        "dayType": "workday",
        "location": location,
        "shiftStart": shift_start or work_start,
        "shiftEnd": shift_end or work_end,
    }
