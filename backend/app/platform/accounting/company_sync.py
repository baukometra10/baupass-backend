"""Company master snapshot for WorkPass Lohn (Firma-ID = companies.id)."""
from __future__ import annotations

from typing import Any

from .keys import require_company_id


def company_upsert_payload(db, company_id: str) -> dict[str, Any]:
    """
    Fields WorkPass Lohn expects for POST /v1/company/upsert style sync.
    company.id is mandatory — without it the request must be rejected.
    """
    company_id = require_company_id(company_id)
    row = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not row:
        raise LookupError("company_not_found")
    data = dict(row)

    def _s(*keys: str) -> str:
        for key in keys:
            val = data.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return ""

    company = {
        "id": company_id,
        "companyId": company_id,
        "name": _s("name", "portal_display_name"),
        "displayName": _s("portal_display_name", "name"),
        "customerNumber": _s("customer_number"),
        "contact": _s("contact"),
        "contactEmail": _s("billing_email", "document_email"),
        "billingEmail": _s("billing_email"),
        "documentEmail": _s("document_email"),
        "address": " ".join(
            part for part in (_s("billing_street"), _s("billing_zip_city")) if part
        ).strip(),
        "billingStreet": _s("billing_street"),
        "billingZipCity": _s("billing_zip_city"),
        "taxId": _s("tax_id", "vat_id"),
        "plan": _s("plan"),
        "status": _s("status") or "active",
        "workStartTime": _s("work_start_time"),
        "workEndTime": _s("work_end_time"),
        "branding": {
            "accentColor": _s("branding_accent_color"),
            "preset": _s("branding_preset"),
            "logoData": _s("branding_logo_data")[:200_000]
            if _s("branding_logo_data")
            else "",
        },
    }
    return {
        "ok": True,
        "product": "WorkPass Lohn",
        "company": company,
        # Flat aliases for /v1/company/upsert clients
        **company,
    }
