"""Monthly accounting handoff job (request only — human confirms before delivery)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import repository as repo
from .hours_service import normalize_period
from .service import request_period_handoff


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
    On run_day (per company), open a pending period handoff request for Ops confirmation.
    Does NOT auto-deliver employees/hours to Lohn and does NOT auto-approve payslips.
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
        existing = repo.get_period_request(db, company_id=company_id, period=target_period)
        if not force and existing and str(existing.get("status") or "") in {
            "pending_confirmation",
            "confirmed",
            "delivered",
        }:
            results.append(
                {
                    "companyId": company_id,
                    "skipped": "already_requested",
                    "period": target_period,
                    "status": existing.get("status"),
                }
            )
            continue
        try:
            out = request_period_handoff(
                db,
                company_id=company_id,
                period=target_period,
                source="monthly_job",
                note="Monatlicher Lauf — bitte Bestätigung für Übergabe an WorkPass Lohn",
            )
            results.append({"companyId": company_id, **out})
        except Exception as exc:
            results.append({"companyId": company_id, "ok": False, "error": str(exc)[:200]})
    return {
        "ok": True,
        "period": target_period,
        "companies": len(integrations),
        "results": results,
        "note": "Handoff waits for human confirmation in Ops — no auto delivery",
    }
