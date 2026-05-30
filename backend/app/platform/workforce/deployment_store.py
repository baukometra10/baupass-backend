"""Per-worker daily deployment locations (Einsatzplan)."""
from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def month_bounds(year: int, month: int) -> tuple[str, str]:
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def list_deployment_days(
    db,
    *,
    company_id: str,
    worker_id: str,
    year: int,
    month: int,
) -> list[dict[str, Any]]:
    start, end = month_bounds(year, month)
    try:
        rows = db.execute(
            """
            SELECT id, work_date, location_label, shift_start, shift_end, notes, source, updated_at
            FROM worker_deployment_days
            WHERE company_id = ? AND worker_id = ? AND work_date >= ? AND work_date <= ?
            ORDER BY work_date ASC
            """,
            (str(company_id), str(worker_id), start, end),
        ).fetchall()
    except Exception:
        return []
    return [dict(r) for r in rows]


def upsert_deployment_days(
    db,
    *,
    company_id: str,
    worker_id: str,
    days: list[dict[str, Any]],
    source: str = "manual",
) -> dict[str, Any]:
    saved = 0
    for item in days:
        work_date = str(item.get("date") or item.get("workDate") or "").strip()[:10]
        location = str(item.get("location") or item.get("locationLabel") or "").strip()
        if not work_date or not location:
            continue
        notes = str(item.get("notes") or "").strip()[:500]
        shift_start = str(item.get("shiftStart") or item.get("shift_start") or "").strip()[:16]
        shift_end = str(item.get("shiftEnd") or item.get("shift_end") or "").strip()[:16]
        row_id = f"wdd-{uuid.uuid4().hex[:12]}"
        db.execute(
            """
            INSERT INTO worker_deployment_days
                (id, company_id, worker_id, work_date, location_label, shift_start, shift_end, notes, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, worker_id, work_date) DO UPDATE SET
                location_label = excluded.location_label,
                shift_start = excluded.shift_start,
                shift_end = excluded.shift_end,
                notes = excluded.notes,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                row_id,
                str(company_id),
                str(worker_id),
                work_date,
                location,
                shift_start,
                shift_end,
                notes,
                source,
                _now_iso(),
            ),
        )
        saved += 1
    db.commit()
    if saved:
        try:
            from .deployment_month import mark_month_edited

            for item in days:
                wd = str(item.get("date") or item.get("workDate") or "")[:10]
                if len(wd) >= 7:
                    mark_month_edited(db, str(company_id), int(wd[:4]), int(wd[5:7]))
                    break
        except Exception:
            pass
    return {"ok": True, "saved": saved}


def sync_from_shift_assignments(
    db,
    *,
    company_id: str,
    worker_id: str,
    year: int,
    month: int,
) -> dict[str, Any]:
    """Map shift_assignments in month to one location per calendar day."""
    start, end = month_bounds(year, month)
    try:
        rows = db.execute(
            """
            SELECT id, site, start_time, end_time, notes
            FROM shift_assignments
            WHERE company_id = ? AND worker_id = ? AND status != 'cancelled'
              AND date(start_time) <= ? AND date(end_time) >= ?
            ORDER BY start_time ASC
            """,
            (str(company_id), str(worker_id), end, start),
        ).fetchall()
    except Exception:
        return {"ok": False, "error": "shift_table_unavailable"}

    by_date: dict[str, dict] = {}
    for r in rows:
        try:
            st = str(r["start_time"] or "")[:10]
            if not st:
                continue
            if st < start or st > end:
                continue
            by_date[st] = {
                "date": st,
                "location": str(r["site"] or "").strip() or "—",
                "shiftStart": str(r["start_time"] or "")[:16],
                "shiftEnd": str(r["end_time"] or "")[:16],
                "notes": str(r["notes"] or "").strip(),
            }
        except Exception:
            continue

    if not by_date:
        return {"ok": True, "saved": 0, "message": "no_shifts_in_month"}

    result = upsert_deployment_days(
        db,
        company_id=company_id,
        worker_id=worker_id,
        days=list(by_date.values()),
        source="shift_sync",
    )
    result["daysFromShifts"] = len(by_date)
    return result


def fill_rotation_template(
    db,
    *,
    company_id: str,
    worker_id: str,
    year: int,
    month: int,
    locations: list[str],
    skip_weekends: bool = False,
) -> dict[str, Any]:
    """Cycle locations across weekdays in month (optional weekend skip)."""
    locs = [str(x).strip() for x in locations if str(x).strip()]
    if not locs:
        return {"ok": False, "error": "locations_required"}
    start_d = date(year, month, 1)
    last = calendar.monthrange(year, month)[1]
    days: list[dict] = []
    idx = 0
    for day_num in range(1, last + 1):
        d = date(year, month, day_num)
        if skip_weekends and d.weekday() >= 5:
            continue
        days.append(
            {
                "date": d.isoformat(),
                "location": locs[idx % len(locs)],
                "notes": "",
            }
        )
        idx += 1
    result = upsert_deployment_days(
        db,
        company_id=company_id,
        worker_id=worker_id,
        days=days,
        source="rotation_template",
    )
    result["templateDays"] = len(days)
    return result


def build_month_calendar(
    db,
    *,
    company_id: str,
    worker_id: str,
    year: int,
    month: int,
    lang: str = "de",
) -> list[dict[str, Any]]:
    """Full month grid with stored or empty locations."""
    weekday_names = {
        "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
        "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "ar": ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"],
    }
    names = weekday_names.get(lang[:2], weekday_names["de"])
    stored = {str(r["work_date"]): r for r in list_deployment_days(db, company_id=company_id, worker_id=worker_id, year=year, month=month)}
    last = calendar.monthrange(year, month)[1]
    out: list[dict] = []
    for day_num in range(1, last + 1):
        d = date(year, month, day_num)
        key = d.isoformat()
        row = stored.get(key)
        rd = dict(row) if row else {}
        out.append(
            {
                "date": key,
                "weekday": names[d.weekday()],
                "weekdayIndex": d.weekday(),
                "location": str(rd.get("location_label") or ""),
                "shiftStart": str(rd.get("shift_start") or ""),
                "shiftEnd": str(rd.get("shift_end") or ""),
                "notes": str(rd.get("notes") or ""),
                "isWeekend": d.weekday() >= 5,
            }
        )
    return out
