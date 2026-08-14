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
    return attendance_from_access_pairs(events)["hours"]


def days_from_access_pairs(events: list[dict[str, Any]]) -> int:
    """Count distinct calendar days with at least one completed check-in → check-out."""
    return int(attendance_from_access_pairs(events)["days"])


def attendance_from_access_pairs(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Pair chronological check-in → check-out; return hours + worked days."""
    open_in: datetime | None = None
    total = timedelta(0)
    day_keys: set[str] = set()
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
                day_keys.add(open_in.strftime("%Y-%m-%d"))
            open_in = None
    return {
        "hours": round(total.total_seconds() / 3600.0, 2),
        "days": len(day_keys),
    }


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def normalize_tax_class(raw: Any) -> str:
    """Map Steuerklasse inputs like 1/I/klasse 1 → Roman I–VI for WorkPass Lohn."""
    text = str(raw or "").strip().upper().replace(" ", "")
    if not text:
        return ""
    text = (
        text.replace("STEUERKLASSE", "")
        .replace("TAXCLASS", "")
        .replace("SK", "")
        .replace("KLASSE", "")
        .replace("CLASS", "")
        .strip("-:_=")
    )
    mapping = {
        "1": "I",
        "01": "I",
        "I": "I",
        "2": "II",
        "02": "II",
        "II": "II",
        "3": "III",
        "03": "III",
        "III": "III",
        "4": "IV",
        "04": "IV",
        "IV": "IV",
        "5": "V",
        "05": "V",
        "V": "V",
        "6": "VI",
        "06": "VI",
        "VI": "VI",
    }
    if text in mapping:
        return mapping[text]
    # Keep already-valid roman fragments mixed with noise, e.g. "I."
    cleaned = re.sub(r"[^IVX0-9]", "", text)
    return mapping.get(cleaned, text if text in {"I", "II", "III", "IV", "V", "VI"} else "")


def full_employee_name(first_name: str = "", last_name: str = "", *, fallback: str = "") -> str:
    name = " ".join(part for part in (str(first_name or "").strip(), str(last_name or "").strip()) if part).strip()
    return name or str(fallback or "").strip()


def lohn_employee_block(row: dict[str, Any]) -> dict[str, Any]:
    """Nested employee object expected by WorkPass Lohn payroll/employees APIs."""
    first = str(row.get("firstName") or "").strip()
    last = str(row.get("lastName") or "").strip()
    name = full_employee_name(first, last, fallback=str(row.get("name") or ""))
    hourly = float(row.get("hourlyRate") or row.get("stundenlohn") or 0)
    insurance = str(row.get("insuranceNumber") or row.get("insuranceNo") or "").strip()
    health = str(row.get("healthFund") or row.get("krankenkasse") or row.get("healthInsurance") or "").strip()
    iban = str(row.get("iban") or ((row.get("bank") or {}) if isinstance(row.get("bank"), dict) else {}).get("iban") or "").replace(" ", "").upper()
    bank_name = str(
        row.get("bankName")
        or ((row.get("bank") or {}) if isinstance(row.get("bank"), dict) else {}).get("name")
        or ""
    ).strip()
    tax_class = normalize_tax_class(row.get("taxClass") or row.get("steuerklasse") or "")
    hours = float(row.get("hours") or ((row.get("attendance") or {}) if isinstance(row.get("attendance"), dict) else {}).get("hours") or 0)
    monthly = float(row.get("salaryGrossMonthly") or 0)
    if hours > 0 and hourly > 0:
        brutto = round(hours * hourly, 2)
    elif monthly > 0:
        brutto = round(monthly, 2)
    else:
        brutto = round(float(row.get("grossEstimate") or row.get("brutto") or row.get("bruttoHint") or 0), 2)
    block: dict[str, Any] = {
        "badgeId": str(row.get("badgeId") or "").strip(),
        "name": name,
        "firstName": first,
        "lastName": last,
        "workerId": str(row.get("workerId") or row.get("employeeId") or "").strip(),
        "employeeId": str(row.get("employeeId") or row.get("workerId") or "").strip(),
        "personnelNumber": str(row.get("personnelNumber") or row.get("personalnummer") or "").strip(),
        "personalnummer": str(row.get("personnelNumber") or row.get("personalnummer") or "").strip(),
        "taxClass": tax_class,
        "steuerklasse": tax_class,
        "hourlyRate": hourly,
        "stundenlohn": hourly,
        "salaryGrossMonthly": monthly,
        "brutto": brutto,
        "gross": brutto,
        "insuranceNo": insurance,
        "insuranceNumber": insurance,
        "healthFund": health,
        "krankenkasse": health,
        "healthInsurance": health,
        "taxId": str(row.get("taxId") or "").strip(),
        "birthDate": str(row.get("birthDate") or "").strip(),
        "email": str(row.get("email") or "").strip(),
        "phone": str(row.get("phone") or "").strip(),
        "address": str(row.get("address") or "").strip(),
        "nationality": str(row.get("nationality") or "").strip(),
        "gender": str(row.get("gender") or "").strip(),
        "jobTitle": str(row.get("jobTitle") or row.get("role") or "").strip(),
        "startDate": str(row.get("startDate") or "").strip(),
        "weeklyHours": str(row.get("weeklyHours") or "").strip(),
        "currency": str(row.get("currency") or "EUR").strip() or "EUR",
        "iban": iban,
        "bankName": bank_name,
        "bank": {"name": bank_name, "iban": iban},
        "status": str(row.get("status") or "").strip(),
        "role": str(row.get("role") or row.get("jobTitle") or "").strip(),
        "site": str(row.get("site") or "").strip(),
        "contractId": row.get("contractId"),
        "contractStatus": row.get("contractStatus"),
    }
    return block


def lohn_attendance_block(row: dict[str, Any]) -> dict[str, Any]:
    hours = float(row.get("hours") or ((row.get("attendance") or {}) if isinstance(row.get("attendance"), dict) else {}).get("hours") or 0)
    days = int(row.get("days") or ((row.get("attendance") or {}) if isinstance(row.get("attendance"), dict) else {}).get("days") or 0)
    return {"hours": round(hours, 2), "days": days}


def lohn_wage_types(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Explicit Lohnarten so WorkPass Lohn can fill Brutto without a second guess."""
    hourly = float(row.get("hourlyRate") or row.get("stundenlohn") or 0)
    hours = float(row.get("hours") or ((row.get("attendance") or {}) if isinstance(row.get("attendance"), dict) else {}).get("hours") or 0)
    monthly = float(row.get("salaryGrossMonthly") or 0)
    currency = str(row.get("currency") or "EUR").strip() or "EUR"
    if hours > 0 and hourly > 0:
        amount = round(hours * hourly, 2)
        return [
            {
                "code": "STD",
                "name": "Stundenlohn",
                "art": "Stundenlohn",
                "hours": round(hours, 2),
                "stunden": round(hours, 2),
                "rate": hourly,
                "satz": hourly,
                "amount": amount,
                "betrag": amount,
                "brutto": amount,
                "currency": currency,
            }
        ]
    if monthly > 0:
        amount = round(monthly, 2)
        return [
            {
                "code": "MONAT",
                "name": "Monatslohn",
                "art": "Monatslohn",
                "hours": 0,
                "stunden": 0,
                "rate": amount,
                "satz": amount,
                "amount": amount,
                "betrag": amount,
                "brutto": amount,
                "currency": currency,
            }
        ]
    return []


def enrich_lohn_compat_fields(row: dict[str, Any], *, include_attendance: bool = False) -> dict[str, Any]:
    """Keep flat fields for older consumers and add Lohn nested aliases."""
    out = dict(row)
    if include_attendance:
        attendance = lohn_attendance_block(out)
        out["hours"] = attendance["hours"]
        out["days"] = attendance["days"]
        out["attendance"] = attendance
    employee = lohn_employee_block(out)
    out["name"] = employee["name"]
    out["insuranceNo"] = employee["insuranceNo"]
    out["insuranceNumber"] = employee["insuranceNumber"]
    out["healthFund"] = employee["healthFund"]
    out["krankenkasse"] = employee["krankenkasse"]
    out["healthInsurance"] = employee["healthInsurance"]
    out["stundenlohn"] = employee["stundenlohn"]
    out["hourlyRate"] = employee["hourlyRate"]
    out["taxClass"] = employee["taxClass"]
    out["steuerklasse"] = employee["steuerklasse"]
    out["personnelNumber"] = employee["personnelNumber"]
    out["personalnummer"] = employee["personalnummer"]
    out["bankName"] = employee["bankName"]
    out["iban"] = employee["iban"]
    out["bank"] = employee["bank"]
    out["brutto"] = employee["brutto"]
    out["gross"] = employee["brutto"]
    out["grossEstimate"] = float(out.get("grossEstimate") or employee["brutto"] or 0)
    out["bruttoHint"] = out["grossEstimate"]
    wage_types = lohn_wage_types(out)
    out["lohnarten"] = wage_types
    out["wageTypes"] = wage_types
    # WorkPass Lohn ingestPayrollBatch reads ONLY empPayload.wageItems (not lohnarten).
    out["wageItems"] = wage_types
    employee["brutto"] = out["brutto"]
    employee["gross"] = out["brutto"]
    employee["lohnarten"] = wage_types
    employee["wageTypes"] = wage_types
    employee["wageItems"] = wage_types
    # Per-employee company must include name — Lohn uses empPayload.company || batch.company
    # and empty name on a present company object blocks fallback to batch.company.name.
    company_obj = out.get("company") if isinstance(out.get("company"), dict) else {}
    company_name = str(
        company_obj.get("name")
        or out.get("companyName")
        or ""
    ).strip()
    company_id = str(company_obj.get("id") or out.get("companyId") or "").strip()
    if company_id:
        out["company"] = {"id": company_id, "name": company_name}
        if company_name:
            out["companyName"] = company_name
    out["employee"] = employee
    out["missingFields"] = _missing_payroll_fields(out, require_hours=include_attendance)
    out["payrollReady"] = len(out["missingFields"]) == 0
    return out


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
        "bankName": "",
        "taxId": "",
        "taxClass": "",
        "healthFund": "",
        "personnelNumber": "",
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
            "employee_bank_name",
            "bank_name",
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
            "health_fund",
            "krankenkasse",
            "health_insurance",
            "tax_class",
            "steuerklasse",
            "personnel_number",
            "personalnummer",
        ):
            if not str(form.get(key) or "").strip() and str(data.get(key) or "").strip():
                form[key] = data[key]
    health_fund = _first_nonempty(
        form.get("health_fund"),
        form.get("healthFund"),
        form.get("krankenkasse"),
        form.get("health_insurance"),
        form.get("healthInsurance"),
        form.get("kk"),
        data.get("health_fund"),
        data.get("krankenkasse"),
        data.get("healthInsurance"),
    )
    bank_name = _first_nonempty(
        form.get("employee_bank_name"),
        form.get("bank_name"),
        form.get("bankName"),
        form.get("iban_bank"),
        data.get("employee_bank_name"),
        data.get("bank_name"),
    )
    tax_class = normalize_tax_class(
        _first_nonempty(
            form.get("tax_class"),
            form.get("taxClass"),
            form.get("steuerklasse"),
            data.get("tax_class"),
            data.get("steuerklasse"),
        )
    )
    personnel_number = _first_nonempty(
        form.get("personnel_number"),
        form.get("personnelNumber"),
        form.get("personalnummer"),
        form.get("personal_number"),
        form.get("employee_number"),
        data.get("personnel_number"),
        data.get("personalnummer"),
    )
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
        "bankName": bank_name,
        "taxId": str(
            form.get("employee_tax_id") or form.get("tax_id") or form.get("taxId") or data.get("employee_tax_id") or ""
        ).strip(),
        "taxClass": tax_class,
        "healthFund": health_fund,
        "personnelNumber": personnel_number,
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


def _missing_payroll_fields(row: dict[str, Any], *, require_hours: bool = False) -> list[str]:
    missing: list[str] = []
    bank = row.get("bank") if isinstance(row.get("bank"), dict) else {}
    attendance = row.get("attendance") if isinstance(row.get("attendance"), dict) else {}
    employee = row.get("employee") if isinstance(row.get("employee"), dict) else {}
    if not str(row.get("iban") or bank.get("iban") or employee.get("iban") or "").strip():
        missing.append("iban")
    if not str(row.get("bankName") or bank.get("name") or employee.get("bankName") or "").strip():
        missing.append("bankName")
    if not str(row.get("taxId") or employee.get("taxId") or "").strip():
        missing.append("taxId")
    insurance = str(
        row.get("insuranceNumber")
        or row.get("insuranceNo")
        or employee.get("insuranceNumber")
        or employee.get("insuranceNo")
        or ""
    ).strip()
    if not insurance:
        missing.append("insuranceNumber")
    health = str(
        row.get("healthFund")
        or row.get("krankenkasse")
        or row.get("healthInsurance")
        or employee.get("healthFund")
        or ""
    ).strip()
    if not health:
        missing.append("healthFund")
    if not str(row.get("birthDate") or employee.get("birthDate") or "").strip():
        missing.append("birthDate")
    tax_class = normalize_tax_class(row.get("taxClass") or row.get("steuerklasse") or employee.get("taxClass") or "")
    if not tax_class:
        missing.append("taxClass")
    hourly = float(row.get("hourlyRate") or row.get("stundenlohn") or employee.get("hourlyRate") or 0)
    monthly = float(row.get("salaryGrossMonthly") or employee.get("salaryGrossMonthly") or 0)
    if hourly <= 0 and monthly <= 0:
        missing.append("payRate")
    if require_hours:
        hours = float(row.get("hours") or attendance.get("hours") or 0)
        if hours <= 0 and hourly > 0:
            missing.append("attendance.hours")
        brutto = float(row.get("brutto") or row.get("grossEstimate") or employee.get("brutto") or 0)
        if brutto <= 0 and (hours > 0 or monthly > 0):
            missing.append("brutto")
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
    badge = _worker_row_value(worker, "badge_id")
    first = _worker_row_value(worker, "first_name")
    last = _worker_row_value(worker, "last_name")
    personnel = master.get("personnelNumber") or badge
    item = {
        "companyId": company_id,
        "workerId": wid,
        "employeeId": wid,
        "firstName": first,
        "lastName": last,
        "name": full_employee_name(first, last),
        "badgeId": badge,
        "personnelNumber": personnel,
        "personalnummer": personnel,
        "insuranceNumber": _worker_row_value(worker, "insurance_number"),
        "insuranceNo": _worker_row_value(worker, "insurance_number"),
        "healthFund": master.get("healthFund") or "",
        "krankenkasse": master.get("healthFund") or "",
        "healthInsurance": master.get("healthFund") or "",
        "taxClass": master.get("taxClass") or "",
        "steuerklasse": master.get("taxClass") or "",
        "status": _worker_row_value(worker, "status"),
        "role": _worker_row_value(worker, "role") or master.get("jobTitle") or "",
        "site": _worker_row_value(worker, "site"),
        "iban": master["iban"],
        "bankName": master.get("bankName") or "",
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
        "stundenlohn": master["hourlyRate"],
        "salaryGrossMonthly": master["salaryGrossMonthly"],
        "currency": master["currency"] or "EUR",
        "contractId": master.get("contractId"),
        "contractStatus": master.get("contractStatus"),
    }
    return enrich_lohn_compat_fields(item, include_attendance=False)


def get_employee_master_item(
    db,
    *,
    company_id: str,
    worker_id: str = "",
    badge_id: str = "",
) -> dict[str, Any] | None:
    """Single employee master row for Lohn push after missing-data fix."""
    company_id = require_company_id(company_id)
    worker_id = str(worker_id or "").strip()
    badge_id = str(badge_id or "").strip()
    worker = None
    if worker_id:
        worker = db.execute(
            """
            SELECT *
            FROM workers
            WHERE id = ? AND company_id = ? AND deleted_at IS NULL
            LIMIT 1
            """,
            (worker_id, company_id),
        ).fetchone()
    if not worker and badge_id:
        worker = db.execute(
            """
            SELECT *
            FROM workers
            WHERE company_id = ? AND deleted_at IS NULL AND badge_id = ?
            LIMIT 1
            """,
            (company_id, badge_id),
        ).fetchone()
    if not worker:
        return None
    return _employee_master_item_from_worker(db, company_id=company_id, worker=worker)


def aggregate_company_hours(
    db,
    *,
    company_id: str,
    period: str,
    worker_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build payroll hours payload for one company/period."""
    company_id = require_company_id(company_id)
    period = normalize_period(period)
    start, end = period_bounds(period)
    wanted = {str(w).strip() for w in (worker_ids or []) if str(w or "").strip()}
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
        if wanted and wid not in wanted:
            continue
        events = db.execute(
            """
            SELECT direction, timestamp
            FROM access_logs
            WHERE worker_id = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
            """,
            (wid, start, end),
        ).fetchall()
        attendance = attendance_from_access_pairs([dict(e) for e in events])
        hours = float(attendance["hours"])
        days = int(attendance["days"])
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
        first = _worker_row_value(worker, "first_name")
        last = _worker_row_value(worker, "last_name")
        badge = _worker_row_value(worker, "badge_id")
        insurance = _worker_row_value(worker, "insurance_number")
        personnel = master.get("personnelNumber") or badge
        health = master.get("healthFund") or ""
        bank_name = master.get("bankName") or ""
        tax_class = master.get("taxClass") or ""
        row = {
            "companyId": company_id,
            "company": {"id": company_id, "name": ""},  # name filled after company lookup + enrich
            "workerId": wid,
            "employeeId": wid,
            "storageKey": storage_key,
            "firstName": first,
            "lastName": last,
            "name": full_employee_name(first, last),
            "badgeId": badge,
            "personnelNumber": personnel,
            "personalnummer": personnel,
            "insuranceNumber": insurance,
            "insuranceNo": insurance,
            "healthFund": health,
            "krankenkasse": health,
            "healthInsurance": health,
            "taxClass": tax_class,
            "steuerklasse": tax_class,
            "status": _worker_row_value(worker, "status"),
            "role": _worker_row_value(worker, "role") or master.get("jobTitle") or "",
            "site": _worker_row_value(worker, "site"),
            "iban": master["iban"],
            "bankName": bank_name,
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
            "days": days,
            "hourlyRate": hourly,
            "stundenlohn": hourly,
            "salaryGrossMonthly": monthly_salary,
            "grossEstimate": gross_estimate,
            "bruttoHint": gross_estimate,
            "payBasis": pay_basis,
            "currency": master.get("currency") or "EUR",
            "contractId": master.get("contractId"),
            "contractStatus": master.get("contractStatus"),
            "note": "grossEstimate is platform hint only; WorkPass Lohn computes official payroll. Brutto = hours × hourlyRate when hourly.",
        }
        rows_out.append(enrich_lohn_compat_fields(row, include_attendance=True))

    company = db.execute("SELECT id, name FROM companies WHERE id = ?", (company_id,)).fetchone()
    company_name = (company["name"] if company else "") or ""
    company_ref = {"id": company_id, "name": company_name}
    for r in rows_out:
        r["companyId"] = company_id
        r["companyName"] = company_name
        r["company"] = dict(company_ref)
    incomplete = [r for r in rows_out if not r.get("payrollReady")]
    return {
        "ok": True,
        "format": "suppix_workpass_lohn_hours_v1",
        "kind": "platform.payroll.batch.v1",
        "product": "WorkPass Lohn",
        "companyId": company_id,
        "company": company_ref,
        "companyName": company_name,
        "period": period,
        "periodStart": start,
        "periodEnd": end,
        "rowCount": len(rows_out),
        "employeeCount": len(rows_out),
        "payrollReadyCount": len(rows_out) - len(incomplete),
        "incompleteCount": len(incomplete),
        "totalHours": round(sum(float(r["hours"]) for r in rows_out), 2),
        "totalDays": sum(int(r.get("days") or 0) for r in rows_out),
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
                "name": r.get("name") or full_employee_name(r.get("firstName") or "", r.get("lastName") or ""),
                "badgeId": r.get("badgeId") or "",
                "missingFields": r["missingFields"],
            }
            for r in incomplete
        ],
    }
