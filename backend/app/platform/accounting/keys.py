"""WorkPass Lohn tenant keys — company-scoped, never name-based."""
from __future__ import annotations


def require_company_id(value: str | None) -> str:
    company_id = (value or "").strip()
    if not company_id:
        raise ValueError("company_id_required")
    return company_id


def payroll_storage_key(*, company_id: str, employee_id: str, period: str) -> str:
    """Canonical payroll row key: companyId::employeeId::period."""
    cid = require_company_id(company_id)
    eid = (employee_id or "").strip()
    per = (period or "").strip()
    if not eid:
        raise ValueError("employee_id_required")
    if not per:
        raise ValueError("period_required")
    return f"{cid}::{eid}::{per}"


def invoice_storage_key(*, company_id: str, invoice_number: str) -> str:
    """Canonical invoice key: companyId::invoiceNumber (no cross-tenant collisions)."""
    cid = require_company_id(company_id)
    num = (invoice_number or "").strip()
    if not num:
        raise ValueError("invoice_number_required")
    return f"{cid}::{num}"


def parse_payroll_storage_key(key: str) -> dict[str, str]:
    parts = (key or "").split("::")
    if len(parts) != 3 or not all(parts):
        raise ValueError("invalid_payroll_storage_key")
    return {"companyId": parts[0], "employeeId": parts[1], "period": parts[2]}
