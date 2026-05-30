"""DATEV payroll CSV attachment for report emails."""
from __future__ import annotations

from typing import Any


def build_datev_csv_attachment(db, company_id: str, *, period: str = "") -> dict[str, Any] | None:
    from backend.app.platform.enterprise.payroll_adapter import build_datev_payroll_csv
    from backend.server import now_iso

    company_id = str(company_id or "").strip()
    if not company_id:
        return None
    period_val = (period or now_iso()[:7]).strip()[:7]
    try:
        csv_text = build_datev_payroll_csv(db, company_id, period=period_val)
    except Exception:
        return None
    if not str(csv_text or "").strip():
        return None
    filename = f"datev-lohn-{company_id}-{period_val}.csv"
    return {
        "data": csv_text.encode("utf-8-sig"),
        "maintype": "text",
        "subtype": "csv",
        "filename": filename,
    }
