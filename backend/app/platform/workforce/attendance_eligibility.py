"""Rules for automatic attendance (proximity login, site auto check-in)."""
from __future__ import annotations

from datetime import date, datetime, time
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


def _within_shift_window(shift_start: str, shift_end: str, *, now: datetime | None = None) -> bool:
    start_raw = _shift_hhmm(shift_start)
    end_raw = _shift_hhmm(shift_end)
    if not start_raw or not end_raw:
        return True
    current = now or datetime.now()
    try:
        sh, sm = (int(x) for x in start_raw.split(":"))
        eh, em = (int(x) for x in end_raw.split(":"))
    except (TypeError, ValueError):
        return True
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em
    current_minutes = current.hour * 60 + current.minute
    window_start = start_minutes - 30
    # Night shift: end before start (e.g. 22:00–06:00)
    if end_minutes < start_minutes:
        return current_minutes >= window_start or current_minutes <= end_minutes
    return window_start <= current_minutes <= end_minutes


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
    location = str((deployment_row or {}).get("location_label") or "").strip()
    shift_start = str((deployment_row or {}).get("shift_start") or "").strip()
    shift_end = str((deployment_row or {}).get("shift_end") or "").strip()

    if plan_active:
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
        if shift_start and shift_end and not _within_shift_window(shift_start, shift_end, now=current):
            return {
                "ok": False,
                "reason": "outside_shift_window",
                "message": sector_attendance_message(db, company_id, "attendanceOutsideShift", lang=lang),
                "dayType": "scheduled",
                "location": location,
                "shiftStart": shift_start,
                "shiftEnd": shift_end,
            }
        return {
            "ok": True,
            "reason": "scheduled",
            "message": "",
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
