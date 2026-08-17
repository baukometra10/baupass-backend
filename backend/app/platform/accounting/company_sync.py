"""Company master snapshot for WorkPass Lohn (Firma-ID = companies.id)."""
from __future__ import annotations

from typing import Any

from .keys import require_company_id

# Platform / product marks must never be sent to WorkPass Lohn as a mandant logo.
_PLATFORM_LOGO_MARKERS = (
    "suppix",
    "baupass",
    "baukometra",
    "worker-icon",
    "suppix-ai-logo",
    "suppix-ai-invoice",
    "suppix-ai-mark",
)


def is_platform_brand_mark(logo: str) -> bool:
    raw = str(logo or "").strip().lower()
    if not raw:
        return False
    return any(marker in raw for marker in _PLATFORM_LOGO_MARKERS)


def company_logo_data_url(db, company_id: str) -> str:
    """
    Mandant Firmenlogo for WorkPass Lohn.

    Prefer companies.branding_logo_data. Never return the SUPPIX/platform mark.
    """
    company_id = require_company_id(company_id)
    try:
        row = db.execute(
            "SELECT branding_logo_data FROM companies WHERE id = ?",
            (company_id,),
        ).fetchone()
    except Exception:
        row = None
    if not row:
        return ""
    data = dict(row)
    logo = str(data.get("branding_logo_data") or "").strip()
    if not logo or is_platform_brand_mark(logo):
        return ""
    return logo


def attach_company_logo(payload: dict[str, Any], logo: str) -> dict[str, Any]:
    """Copy logo bytes onto upsert/pull shapes Lohn already consumes."""
    logo = str(logo or "").strip()
    branding = dict(payload.get("branding") or {})
    branding["hasLogo"] = bool(logo)
    branding["logoData"] = logo
    payload["branding"] = branding
    payload["logoData"] = logo
    payload["hasLogo"] = bool(logo)
    company = payload.get("company")
    if isinstance(company, dict):
        nested = dict(company)
        nested_branding = dict(nested.get("branding") or branding)
        nested_branding["hasLogo"] = bool(logo)
        nested_branding["logoData"] = logo
        nested["branding"] = nested_branding
        nested["logoData"] = logo
        nested["hasLogo"] = bool(logo)
        payload["company"] = nested
    return payload


def company_upsert_payload(db, company_id: str, *, include_logo: bool = False) -> dict[str, Any]:
    """
    Fields WorkPass Lohn expects for POST /v1/company/upsert style sync.
    company.id is mandatory — without it the request must be rejected.

    Default omit raw logo bytes: large base64 holds SQLite writers during outbound
    HTTP. Inbound Lohn pulls and explicit logo handoff set include_logo=True.
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

    stored_logo = _s("branding_logo_data")
    has_logo = bool(stored_logo) and not is_platform_brand_mark(stored_logo)
    logo_data = stored_logo if (include_logo and has_logo) else ""

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
            "hasLogo": has_logo,
            "logoData": logo_data,
        },
        "hasLogo": has_logo,
        "logoData": logo_data,
    }
    return {
        "ok": True,
        "product": "WorkPass Lohn",
        "company": company,
        # Flat aliases for /v1/company/upsert clients
        **company,
    }
