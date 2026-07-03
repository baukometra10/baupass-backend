"""Worker responses to scheduled deployment days (decline / undo)."""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _business_today() -> date:
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(os.getenv("BAUPASS_BUSINESS_TZ", "Europe/Berlin"))
        return datetime.now(tz).date()
    except Exception:
        return datetime.now(timezone.utc).date()


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
) -> list[dict[str, Any]]:
    from .deployment_store import month_bounds

    start, end = month_bounds(year, month)
    try:
        rows = db.execute(
            """
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
