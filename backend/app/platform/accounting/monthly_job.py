"""Monthly accounting hours export job (safe; no auto-approve of statements)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import repository as repo
from .hours_service import normalize_period
from .service import notify_hours_ready


def previous_period(reference: datetime | None = None) -> str:
    now = reference or datetime.now(timezone.utc)
    year, month = now.year, now.month
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def run_monthly_accounting_exports(
    db,
    *,
    reference_date: datetime | None = None,
    force: bool = False,
    period: str | None = None,
) -> dict[str, Any]:
    """
    On run_day (per company), prepare previous month's payroll batch and push/notify Lohn.
    Does NOT release payslips to workers.
    """
    now = reference_date or datetime.now(timezone.utc)
    target_period = normalize_period(period) if period else previous_period(now)
    integrations = repo.list_enabled_integrations(db)
    results: list[dict[str, Any]] = []
    for integ in integrations:
        company_id = str(integ["company_id"])
        run_day = int(integ.get("run_day") or 1)
        if not force and int(now.day) != run_day:
            results.append({"companyId": company_id, "skipped": "not_run_day", "runDay": run_day})
            continue
        if not force and str(integ.get("last_export_period") or "") == target_period:
            existing = repo.get_hour_export(db, company_id=company_id, period=target_period)
            if existing and existing.get("status") in {"sent", "acked", "queued"}:
                results.append({"companyId": company_id, "skipped": "already_exported", "period": target_period})
                continue
        try:
            # notify_hours_ready: prepare platform.payroll.batch.v1, webhook + POST /v1/payroll/batch
            out = notify_hours_ready(db, company_id=company_id, period=target_period)
            results.append({"companyId": company_id, **out})
        except Exception as exc:
            results.append({"companyId": company_id, "ok": False, "error": str(exc)[:200]})
    return {
        "ok": True,
        "period": target_period,
        "companies": len(integrations),
        "results": results,
    }
