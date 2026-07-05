"""E2E security policy — enforced by default for maximum protection."""
from __future__ import annotations

import os
from typing import Any


def _env_truthy(name: str, default: str = "1") -> bool:
    return str(os.getenv(name, default) or default).strip().lower() in {"1", "true", "yes", "on"}


def e2e_chat_required() -> bool:
    """When true, chat messages must be E2E envelopes (no plaintext). Default: on."""
    return _env_truthy("BAUPASS_E2E_CHAT_REQUIRED", "1")


def e2e_sensitive_fields_required() -> bool:
    """When true, leave notes, contract drafts, etc. must be E2E. Default: on."""
    return _env_truthy("BAUPASS_E2E_SENSITIVE_REQUIRED", "1")


def e2e_attachments_required() -> bool:
    """When true, chat attachments must be client-encrypted. Default: on."""
    return _env_truthy("BAUPASS_E2E_ATTACHMENTS_REQUIRED", "1")


def company_e2e_settings(db, company_id: str) -> dict[str, Any]:
    """Per-company overrides from companies.settings_json (optional)."""
    cid = str(company_id or "").strip()
    if not cid or db is None:
        return {}
    try:
        row = db.execute(
            "SELECT settings_json FROM companies WHERE id = ? AND deleted_at IS NULL",
            (cid,),
        ).fetchone()
        if not row:
            return {}
        import json

        payload = json.loads(str(row[0] if isinstance(row, tuple) else row["settings_json"] or "{}"))
        security = payload.get("security") if isinstance(payload, dict) else {}
        return security if isinstance(security, dict) else {}
    except Exception:
        return {}


def is_e2e_chat_required(db, company_id: str) -> bool:
    overrides = company_e2e_settings(db, company_id)
    if overrides.get("e2e_chat_enabled") is False:
        return False
    if overrides.get("e2e_chat_enabled") is True:
        return True
    return e2e_chat_required()


def is_e2e_attachment_required(db, company_id: str) -> bool:
    overrides = company_e2e_settings(db, company_id)
    if overrides.get("e2e_attachments_required") is False:
        return False
    if overrides.get("e2e_attachments_required") is True:
        return True
    return e2e_attachments_required()


def is_e2e_sensitive_required(db, company_id: str) -> bool:
    overrides = company_e2e_settings(db, company_id)
    if overrides.get("e2e_sensitive_required") is False:
        return False
    if overrides.get("e2e_sensitive_required") is True:
        return True
    return e2e_sensitive_fields_required()
