"""Aggregate monthly worked hours from access_logs + contract hourly rates."""
from __future__ import annotations

import json
import re
from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any

from .keys import payroll_storage_key, require_company_id

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


def _contract_master_for_worker(db, *, company_id: str, worker_id: str) -> dict[str, Any]:
    """Pull payroll-relevant master fields from latest employment contract form."""
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
    empty = {
        "hourlyRate": 0.0,
        "salaryGrossMonthly": 0.0,
        "contractId": None,
        "contractStatus": None,
        "iban": "",
        "taxId": "",
        "birthDate": "",
        "email": "",
        "phone": "",
        "address": "",
        "nationality": "",
        "gender": "",
        "jobTitle": "",
        "startDate": "",
        "weeklyHours": "",
        "currency": "EUR",
    }
    if not row:
        return empty
    try:
        data = json.loads(row["input_json"] or "{}")
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        from backend.app.domains.contracts.validation import extract_form_from_input

        form = extract_form_from_input(data)
    except Exception:
        form = data.get("form") if isinstance(data.get("form"), dict) else data
        if not isinstance(form, dict):
            form = {}
        # Legacy flat keys on input_json root
        for key in (
            "hourly_rate",
            "salary_gross_monthly",
            "employee_iban",
            "employee_tax_id",
            "employee_birth_date",
            "employee_email",
            "employee_phone",
            "employee_address",
            "employee_nationality",
            "employee_gender",
            "job_title",
            "start_date",
            "weekly_hours",
            "iban",
            "tax_id",
            "birth_date",
        ):
            if not str(form.get(key) or "").strip() and str(data.get(key) or "").strip():
                form[key] = data[key]
    return {
        "hourlyRate": _parse_amount(form.get("hourly_rate") or form.get("hourlyRate") or data.get("hourly_rate")),
        "salaryGrossMonthly": _parse_amount(
            form.get("salary_gross_monthly")
            or form.get("gross_monthly")
            or form.get("monthly_salary")
            or form.get("salary")
            or data.get("salary_gross_monthly")
        ),
        "contractId": row["id"],
        "contractStatus": row["status"],
        "iban": str(form.get("employee_iban") or form.get("iban") or data.get("employee_iban") or "").replace(" ", "").upper(),
        "taxId": str(
            form.get("employee_tax_id") or form.get("tax_id") or form.get("taxId") or data.get("employee_tax_id") or ""
        ).strip(),
        "birthDate": str(
            form.get("employee_birth_date") or form.get("birth_date") or data.get("employee_birth_date") or ""
        ).strip()[:10],
        "email": str(form.get("employee_email") or form.get("email") or "").strip(),
        "phone": str(form.get("employee_phone") or form.get("phone") or "").strip(),
        "address": str(form.get("employee_address") or form.get("address") or "").strip(),
        "nationality": str(form.get("employee_nationality") or form.get("nationality") or "").strip(),
        "gender": str(form.get("employee_gender") or form.get("gender") or "").strip(),
        "jobTitle": str(form.get("job_title") or form.get("role") or "").strip(),
        "startDate": str(form.get("start_date") or "").strip()[:10],
        "weeklyHours": str(form.get("weekly_hours") or "").strip(),
        "currency": str(form.get("currency") or "EUR").strip() or "EUR",
    }


def _contract_rate_for_worker(db, *, company_id: str, worker_id: str) -> dict[str, Any]:
    return _contract_master_for_worker(db, company_id=company_id, worker_id=worker_id)


def _worker_row_value(worker, key: str, default: str = "") -> str:
    try:
        if key in worker.keys():
            return str(worker[key] or "").strip() or default
    except Exception:
        pass
    return default


def _missing_payroll_fields(row: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not str(row.get("iban") or "").strip():
        missing.append("iban")
    if not str(row.get("taxId") or "").strip():
        missing.append("taxId")
    if not str(row.get("insuranceNumber") or "").strip():
        missing.append("insuranceNumber")
    if not str(row.get("birthDate") or "").strip():
        missing.append("birthDate")
    if float(row.get("hourlyRate") or 0) <= 0 and float(row.get("salaryGrossMonthly") or 0) <= 0:
        missing.append("payRate")
    return missing


def build_employee_master_list(db, *, company_id: str) -> dict[str, Any]:
    """Full employee master for WorkPass Lohn pull (no hours period required)."""
    company_id = require_company_id(company_id)
    workers = db.execute(
        """
        SELECT *
        FROM workers
        WHERE company_id = ? AND deleted_at IS NULL
        ORDER BY last_name, first_name
        """,
        (company_id,),
    ).fetchall()
    employees: list[dict[str, Any]] = []
    for worker in workers:
        employees.append(_employee_master_item_from_worker(db, company_id=company_id, worker=worker))
    company = db.execute("SELECT id, name FROM companies WHERE id = ?", (company_id,)).fetchone()
    company_name = (company["name"] if company else "") or ""
    ready = sum(1 for e in employees if e.get("payrollReady"))
    return {
        "ok": True,
        "format": "platform.employees.v1",
        "capability": "platform.employees.v1",
        "product": "WorkPass Lohn",
        "companyId": company_id,
        "company": {"id": company_id, "name": company_name},
        "companyName": company_name,
        "employeeCount": len(employees),
        "payrollReadyCount": ready,
        "incompleteCount": len(employees) - ready,
        "employees": employees,
        "note": "Master data for Lohn; hours/payroll-batch still required for period totals",
    }


def _employee_master_item_from_worker(db, *, company_id: str, worker) -> dict[str, Any]:
    wid = str(worker["id"])
    master = _contract_master_for_worker(db, company_id=company_id, worker_id=wid)
    email = master["email"] or _worker_row_value(worker, "contact_email")
    phone = master["phone"] or _worker_row_value(worker, "contact_phone")
    address = master["address"] or _worker_row_value(worker, "home_address")
    birth = master["birthDate"] or _worker_row_value(worker, "birth_date")
    gender = master["gender"] or _worker_row_value(worker, "gender")
    item = {
        "companyId": company_id,
        "workerId": wid,
        "employeeId": wid,
        "firstName": _worker_row_value(worker, "first_name"),
        "lastName": _worker_row_value(worker, "last_name"),
        "badgeId": _worker_row_value(worker, "badge_id"),
        "insuranceNumber": _worker_row_value(worker, "insurance_number"),
        "status": _worker_row_value(worker, "status"),
        "role": _worker_row_value(worker, "role") or master.get("jobTitle") or "",
        "site": _worker_row_value(worker, "site"),
        "iban": master["iban"],
        "taxId": master["taxId"],
        "birthDate": birth,
        "email": email,
        "phone": phone,
        "address": address,
        "nationality": master["nationality"],
        "gender": gender,
        "jobTitle": master["jobTitle"] or _worker_row_value(worker, "role"),
        "startDate": master["startDate"],
        "weeklyHours": master["weeklyHours"],
        "hourlyRate": master["hourlyRate"],
        "salaryGrossMonthly": master["salaryGrossMonthly"],
        "currency": master["currency"] or "EUR",
        "contractId": master.get("contractId"),
        "contractStatus": master.get("contractStatus"),
    }
    item["missingFields"] = _missing_payroll_fields(item)
    item["payrollReady"] = len(item["missingFields"]) == 0
    return item


def get_employee_master_item(db, *, company_id: str, worker_id: str) -> dict[str, Any] | None:
    """Single employee master row for Lohn push after missing-data fix."""
    company_id = require_company_id(company_id)
    worker_id = str(worker_id or "").strip()
    if not worker_id:
        return None
    worker = db.execute(
        """
        SELECT *
        FROM workers
        WHERE id = ? AND company_id = ? AND deleted_at IS NULL
        LIMIT 1
        """,
        (worker_id, company_id),
    ).fetchone()
    if not worker:
        return None
    return _employee_master_item_from_worker(db, company_id=company_id, worker=worker)


def aggregate_company_hours(db, *, company_id: str, period: str) -> dict[str, Any]:
    """Build payroll hours payload for one company/period."""
    company_id = require_company_id(company_id)
    period = normalize_period(period)
    start, end = period_bounds(period)
    workers = db.execute(
        """
        SELECT *
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
        master = _contract_master_for_worker(db, company_id=company_id, worker_id=wid)
        hourly = float(master["hourlyRate"] or 0)
        monthly_salary = float(master["salaryGrossMonthly"] or 0)
        if hourly > 0:
            gross_estimate = round(hours * hourly, 2)
            pay_basis = "hourly"
        elif monthly_salary > 0:
            gross_estimate = round(monthly_salary, 2)
            pay_basis = "monthly_salary"
        else:
            gross_estimate = 0.0
            pay_basis = "unknown"
        storage_key = payroll_storage_key(company_id=company_id, employee_id=wid, period=period)
        email = master["email"] or _worker_row_value(worker, "contact_email")
        phone = master["phone"] or _worker_row_value(worker, "contact_phone")
        address = master["address"] or _worker_row_value(worker, "home_address")
        birth = master["birthDate"] or _worker_row_value(worker, "birth_date")
        gender = master["gender"] or _worker_row_value(worker, "gender")
        row = {
            "companyId": company_id,
            "company": {"id": company_id},
            "workerId": wid,
            "employeeId": wid,
            "storageKey": storage_key,
            "firstName": _worker_row_value(worker, "first_name"),
            "lastName": _worker_row_value(worker, "last_name"),
            "badgeId": _worker_row_value(worker, "badge_id"),
            "insuranceNumber": _worker_row_value(worker, "insurance_number"),
            "status": _worker_row_value(worker, "status"),
            "role": _worker_row_value(worker, "role") or master.get("jobTitle") or "",
            "site": _worker_row_value(worker, "site"),
            "iban": master["iban"],
            "taxId": master["taxId"],
            "birthDate": birth,
            "email": email,
            "phone": phone,
            "address": address,
            "nationality": master["nationality"],
            "gender": gender,
            "jobTitle": master["jobTitle"] or _worker_row_value(worker, "role"),
            "startDate": master["startDate"],
            "weeklyHours": master["weeklyHours"],
            "period": period,
            "hours": hours,
            "hourlyRate": hourly,
            "salaryGrossMonthly": monthly_salary,
            "grossEstimate": gross_estimate,
            "payBasis": pay_basis,
            "currency": master.get("currency") or "EUR",
            "contractId": master.get("contractId"),
            "contractStatus": master.get("contractStatus"),
            "note": "grossEstimate is platform hint only; WorkPass Lohn computes official payroll",
        }
        row["missingFields"] = _missing_payroll_fields(row)
        row["payrollReady"] = len(row["missingFields"]) == 0
        rows_out.append(row)

    company = db.execute("SELECT id, name FROM companies WHERE id = ?", (company_id,)).fetchone()
    company_name = (company["name"] if company else "") or ""
    incomplete = [r for r in rows_out if not r.get("payrollReady")]
    return {
        "ok": True,
        "format": "suppix_workpass_lohn_hours_v1",
        "product": "WorkPass Lohn",
        "companyId": company_id,
        "company": {"id": company_id, "name": company_name},
        "companyName": company_name,
        "period": period,
        "periodStart": start,
        "periodEnd": end,
        "rowCount": len(rows_out),
        "employeeCount": len(rows_out),
        "payrollReadyCount": len(rows_out) - len(incomplete),
        "incompleteCount": len(incomplete),
        "totalHours": round(sum(float(r["hours"]) for r in rows_out), 2),
        "totalGrossEstimate": round(sum(float(r["grossEstimate"]) for r in rows_out), 2),
        "currency": "EUR",
        "tenantIsolation": "companyId::employeeId::period",
        "rows": rows_out,
        "incompleteEmployees": [
            {
                "employeeId": r["employeeId"],
                "workerId": r["workerId"],
                "firstName": r["firstName"],
                "lastName": r["lastName"],
                "missingFields": r["missingFields"],
            }
            for r in incomplete
        ],
    }
