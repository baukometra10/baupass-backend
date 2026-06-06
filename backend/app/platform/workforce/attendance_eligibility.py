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
        SELECT work_date, location_label, shift_start, shift_end, notes
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


def _within_shift_window(shift_start: str, shift_end: str, *, now: datetime | None = None) -> bool:
    start_raw = str(shift_start or "").strip()[:5]
    end_raw = str(shift_end or "").strip()[:5]
    if not start_raw or not end_raw or ":" not in start_raw or ":" not in end_raw:
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
    # Allow check-in from 30 minutes before shift start until shift end.
    return (start_minutes - 30) <= current_minutes <= end_minutes


def worker_may_auto_attend_today(
    db,
    worker: Any,
    *,
    target_date: date | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Decide whether automatic attendance (proximity login / site auto check-in) is allowed.

    Returns {ok, reason, message, dayType, location, shiftStart, shiftEnd}.
    """
    from backend.server import is_company_workday_today, normalize_worker_type

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
            "message": "Heute genehmigter Urlaub – keine automatische Anmeldung.",
            "dayType": "leave",
        }

    response = worker_deployment_response_for_date(
        db, company_id=company_id, worker_id=worker_id, target_date=day
    )
    if response == "declined":
        return {
            "ok": False,
            "reason": "deployment_declined",
            "message": "Einsatztag wurde abgelehnt – keine automatische Anmeldung.",
            "dayType": "declined",
        }

    plan_active = worker_has_deployment_plan_usage(
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
                "message": "Heute frei laut Einsatzplan – keine automatische Anmeldung.",
                "dayType": "free",
                "location": "",
                "shiftStart": shift_start,
                "shiftEnd": shift_end,
            }
        if not _within_shift_window(shift_start, shift_end, now=current):
            return {
                "ok": False,
                "reason": "outside_shift_window",
                "message": "Automatische Anmeldung nur waehrend der geplanten Schichtzeit.",
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

    # No deployment plan in use — fall back to standard workday (Mo–Fr).
    if day == date.today() and not is_company_workday_today():
        return {
            "ok": False,
            "reason": "not_a_workday",
            "message": "Heute kein Arbeitstag.",
            "dayType": "weekend",
        }
    if day.weekday() >= 5:
        return {
            "ok": False,
            "reason": "not_a_workday",
            "message": "Heute kein Arbeitstag.",
            "dayType": "weekend",
        }

    return {
        "ok": True,
        "reason": "workday",
        "message": "",
        "dayType": "workday",
        "location": location,
        "shiftStart": shift_start,
        "shiftEnd": shift_end,
    }
