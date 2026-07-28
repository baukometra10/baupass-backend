"""Aggregate monthly worked hours from access_logs + contract hourly rates."""
from __future__ import annotations

import json
import re
from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any

_PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")
_CHECK_IN = {"check-in", "checkin", "in", "entry", "enter"}
_CHECK_OUT = {"check-out", "checkout", "out", "exit", "leave"}


def normalize_period(period: str) -> str:
    value = (period or "").strip()[:7]
    if not _PERIOD_RE.match(value):
        raise ValueError("invalid_period")
    return value


def period_bounds(period: str) -> tuple[str, str]:
    period = normalize_period(period)
    year, month = int(period[:4]), int(period[5:7])
    last_day = monthrange(year, month)[1]
    start = f"{period}-01T00:00:00"
    end = f"{period}-{last_day:02d}T23:59:59"
    return start, end


def _parse_ts(raw: str) -> datetime | None:
    text = (raw or "").strip().replace("Z", "")
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text[:26])
    except ValueError:
        return None


def _direction_bucket(direction: str) -> str:
    d = (direction or "").strip().lower()
    if d in _CHECK_IN or d.endswith("in") or "check-in" in d:
        return "in"
    if d in _CHECK_OUT or d.endswith("out") or "check-out" in d:
        return "out"
    return ""


def _parse_amount(raw: Any) -> float:
    if raw is None:
        return 0.0
    text = str(raw).strip().replace("€", "").replace(" ", "").replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text:
        return 0.0
    try:
        return round(float(text), 4)
    except ValueError:
        return 0.0


def hours_from_access_pairs(events: list[dict[str, Any]]) -> float:
    """Pair chronological check-in → check-out; ignore open sessions at month end."""
    open_in: datetime | None = None
    total = timedelta(0)
    for event in sorted(events, key=lambda e: str(e.get("timestamp") or "")):
        bucket = _direction_bucket(str(event.get("direction") or ""))
        ts = _parse_ts(str(event.get("timestamp") or ""))
        if not ts or not bucket:
            continue
        if bucket == "in":
            open_in = ts
            continue
        if bucket == "out" and open_in is not None and ts >= open_in:
            delta = ts - open_in
            # Cap single session at 16h to reduce bad punches
            if delta <= timedelta(hours=16):
                total += delta
            open_in = None
    return round(total.total_seconds() / 3600.0, 2)


def _contract_rate_for_worker(db, *, company_id: str, worker_id: str) -> dict[str, Any]:
    row = db.execute(
        """
        SELECT id, status, input_json, updated_at
        FROM employment_contracts
        WHERE company_id = ? AND worker_id = ?
          AND LOWER(COALESCE(status, '')) IN ('signed', 'final', 'active', 'completed', 'done')
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (company_id, worker_id),
    ).fetchone()
    if not row:
        row = db.execute(
            """
            SELECT id, status, input_json, updated_at
            FROM employment_contracts
            WHERE company_id = ? AND worker_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (company_id, worker_id),
        ).fetchone()
    if not row:
        return {"hourlyRate": 0.0, "salaryGrossMonthly": 0.0, "contractId": None, "contractStatus": None}
    try:
        data = json.loads(row["input_json"] or "{}")
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "hourlyRate": _parse_amount(data.get("hourly_rate")),
        "salaryGrossMonthly": _parse_amount(data.get("salary_gross_monthly")),
        "contractId": row["id"],
        "contractStatus": row["status"],
    }


def aggregate_company_hours(db, *, company_id: str, period: str) -> dict[str, Any]:
    """Build payroll hours payload for one company/period."""
    period = normalize_period(period)
    start, end = period_bounds(period)
    workers = db.execute(
        """
        SELECT id, first_name, last_name, badge_id, insurance_number, status
        FROM workers
        WHERE company_id = ? AND deleted_at IS NULL
        ORDER BY last_name, first_name
        """,
        (company_id,),
    ).fetchall()

    rows_out: list[dict[str, Any]] = []
    for worker in workers:
        wid = str(worker["id"])
        events = db.execute(
            """
            SELECT direction, timestamp
            FROM access_logs
            WHERE worker_id = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
            """,
            (wid, start, end),
        ).fetchall()
        hours = hours_from_access_pairs([dict(e) for e in events])
        rate_info = _contract_rate_for_worker(db, company_id=company_id, worker_id=wid)
        hourly = float(rate_info["hourlyRate"] or 0)
        monthly_salary = float(rate_info["salaryGrossMonthly"] or 0)
        if hourly > 0:
            gross_estimate = round(hours * hourly, 2)
            pay_basis = "hourly"
        elif monthly_salary > 0:
            gross_estimate = round(monthly_salary, 2)
            pay_basis = "monthly_salary"
        else:
            gross_estimate = 0.0
            pay_basis = "unknown"
        rows_out.append(
            {
                "workerId": wid,
                "firstName": worker["first_name"] or "",
                "lastName": worker["last_name"] or "",
                "badgeId": worker["badge_id"] or "",
                "insuranceNumber": worker["insurance_number"] or "",
                "status": worker["status"] or "",
                "period": period,
                "hours": hours,
                "hourlyRate": hourly,
                "salaryGrossMonthly": monthly_salary,
                "grossEstimate": gross_estimate,
                "payBasis": pay_basis,
                "currency": "EUR",
                "contractId": rate_info.get("contractId"),
                "note": "grossEstimate is platform hint only; accounting app computes official payroll",
            }
        )

    company = db.execute("SELECT id, name FROM companies WHERE id = ?", (company_id,)).fetchone()
    return {
        "ok": True,
        "format": "suppix_workpass_lohn_hours_v1",
        "product": "WorkPass Lohn",
        "companyId": company_id,
        "companyName": (company["name"] if company else "") or "",
        "period": period,
        "periodStart": start,
        "periodEnd": end,
        "rowCount": len(rows_out),
        "totalHours": round(sum(float(r["hours"]) for r in rows_out), 2),
        "totalGrossEstimate": round(sum(float(r["grossEstimate"]) for r in rows_out), 2),
        "currency": "EUR",
        "rows": rows_out,
    }
