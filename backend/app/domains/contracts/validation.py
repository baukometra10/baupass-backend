from __future__ import annotations

import json
import re
from typing import Any

BASE_REQUIRED = (
    "employee_name",
    "employee_gender",
    "employee_address",
    "job_title",
    "start_date",
    "work_location",
)

FORM_FIELD_KEYS = (
    "employee_name",
    "employee_gender",
    "employee_birth_date",
    "employee_email",
    "employee_phone",
    "employee_address",
    "employee_nationality",
    "employee_work_permit",
    "employee_iban",
    "employee_tax_id",
    "collective_agreement",
    "collective_agreement_name",
    "job_title",
    "jurisdiction",
    "start_date",
    "end_date",
    "work_location",
    "weekly_hours",
    "vacation_days",
    "probation_months",
    "salary_type",
    "currency",
    "salary_gross_monthly",
    "hourly_rate",
)

FIELD_LABELS: dict[str, dict[str, str]] = {
    "employee_name": {"de": "Name des Arbeitnehmers", "en": "Employee name", "ar": "اسم الموظف"},
    "employee_gender": {"de": "Anrede (Herr/Frau)", "en": "Salutation (gender)", "ar": "اللقب (الجنس)"},
    "employee_birth_date": {"de": "Geburtsdatum", "en": "Date of birth", "ar": "تاريخ الميلاد"},
    "employee_address": {"de": "Adresse", "en": "Address", "ar": "العنوان"},
    "job_title": {"de": "Position", "en": "Job title", "ar": "المنصب"},
    "start_date": {"de": "Arbeitsbeginn", "en": "Start date", "ar": "تاريخ البدء"},
    "end_date": {"de": "Vertragsende", "en": "End date", "ar": "تاريخ الانتهاء"},
    "work_location": {"de": "Arbeitsort", "en": "Work location", "ar": "مكان العمل"},
    "weekly_hours": {"de": "Wochenstunden", "en": "Weekly hours", "ar": "ساعات العمل"},
    "salary_gross_monthly": {"de": "Bruttogehalt", "en": "Gross monthly salary", "ar": "الراتب الشهري"},
    "hourly_rate": {"de": "Stundenlohn", "en": "Hourly rate", "ar": "أجر الساعة"},
    "vacation_days": {"de": "Urlaubstage", "en": "Vacation days", "ar": "أيام الإجازة"},
    "probation_months": {"de": "Probezeit", "en": "Probation period", "ar": "فترة التجربة"},
}

_HOURLY_TYPES = {"hourly", "hour", "hourly_wage", "stundenlohn"}
_MONTHLY_TYPES = {"monthly", "monthly_fixed", "fixed", "salary", "monatsgehalt", "monthly_salary"}


def _label(field: str, lang: str) -> str:
    lang = (lang or "de")[:2]
    row = FIELD_LABELS.get(field) or {}
    return row.get(lang) or row.get("en") or field


def _is_empty(value: Any) -> bool:
    return not str(value or "").strip()


def _clean_amount(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    cleaned = re.sub(r"[^\d,.\-]", "", text.replace(" ", ""))
    return cleaned.strip()


def _resolve_salary_type(form: dict[str, Any]) -> str:
    raw_type = str(form.get("salary_type") or "").strip().lower()
    if raw_type in _HOURLY_TYPES:
        return "hourly"
    if raw_type in _MONTHLY_TYPES:
        return "monthly_fixed"
    if not _is_empty(form.get("hourly_rate")) and _is_empty(form.get("salary_gross_monthly")):
        return "hourly"
    return "monthly_fixed"


def normalize_contract_form(form: dict[str, Any] | None) -> dict[str, Any]:
    """Unify legacy/alternate keys and infer salary_type from filled fields."""
    form = dict(form or {})

    if _is_empty(form.get("salary_gross_monthly")):
        for key in ("gross_monthly", "monthly_salary", "salary", "gross_salary", "bruttogehalt"):
            if not _is_empty(form.get(key)):
                form["salary_gross_monthly"] = _clean_amount(form[key])
                break
    else:
        form["salary_gross_monthly"] = _clean_amount(form["salary_gross_monthly"])

    if _is_empty(form.get("hourly_rate")):
        for key in ("hourly_wage", "salary_hourly"):
            val = form.get(key)
            if not _is_empty(val):
                form["hourly_rate"] = _clean_amount(val)
                break
    else:
        form["hourly_rate"] = _clean_amount(form["hourly_rate"])

    salary_type = _resolve_salary_type(form)
    form["salary_type"] = salary_type
    if salary_type == "hourly":
        form["salary_gross_monthly"] = ""
    return form


def extract_form_from_input(input_data: dict[str, Any] | None) -> dict[str, Any]:
    """Read form fields from input_json, including legacy flat keys."""
    input_data = dict(input_data or {})
    form = dict(input_data.get("form") or {})
    for key in FORM_FIELD_KEYS:
        if _is_empty(form.get(key)) and not _is_empty(input_data.get(key)):
            form[key] = input_data[key]
    return normalize_contract_form(form)


def _field_applies(key: str, *, salary_type: str, contract_type: str) -> bool:
    if key == "salary_gross_monthly":
        return salary_type != "hourly" and contract_type != "mini_job"
    if key == "hourly_rate":
        return salary_type == "hourly"
    if key == "end_date":
        return contract_type == "fixed_term"
    return True


def validate_contract_form(
    form: dict[str, Any],
    *,
    template: dict[str, Any] | None = None,
    lang: str = "de",
) -> list[str]:
    """Return human-readable missing field labels (empty list = ok)."""
    form = normalize_contract_form(form)
    lang = (lang or "de")[:2]
    contract_type = str((template or {}).get("contract_type") or "").strip()
    salary_type = str(form.get("salary_type") or "monthly_fixed").strip()

    required: list[str] = list(BASE_REQUIRED)
    if template:
        try:
            extra = json.loads(template.get("required_fields_json") or "[]")
            if isinstance(extra, list):
                for key in extra:
                    key = str(key or "").strip()
                    if key and key not in required:
                        required.append(key)
        except (json.JSONDecodeError, TypeError):
            pass

    if contract_type == "fixed_term" and "end_date" not in required:
        required.append("end_date")
    if salary_type == "hourly":
        if "hourly_rate" not in required:
            required.append("hourly_rate")
    elif contract_type != "mini_job" and "salary_gross_monthly" not in required:
        required.append("salary_gross_monthly")

    missing: list[str] = []
    seen: set[str] = set()
    for key in required:
        if key in seen:
            continue
        seen.add(key)
        if not _field_applies(key, salary_type=salary_type, contract_type=contract_type):
            continue
        if _is_empty(form.get(key)):
            missing.append(_label(key, lang))
    return missing
