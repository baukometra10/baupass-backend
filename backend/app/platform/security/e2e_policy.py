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


def _ensure_worker_e2e_client_column(db) -> None:
    if db is None:
        return
    try:
        cols = {str(row[1] if isinstance(row, tuple) else row["name"]) for row in db.execute("PRAGMA table_info(workers)").fetchall()}
        if "e2e_client_unavailable" not in cols:
            db.execute("ALTER TABLE workers ADD COLUMN e2e_client_unavailable INTEGER NOT NULL DEFAULT 0")
            db.commit()
    except Exception:
        try:
            db.commit()
        except Exception:
            pass


def set_worker_e2e_client_unavailable(db, worker_id: str) -> None:
    wid = str(worker_id or "").strip()
    if not wid or db is None:
        return
    _ensure_worker_e2e_client_column(db)
    db.execute("UPDATE workers SET e2e_client_unavailable = 1 WHERE id = ?", (wid,))
    db.commit()


def clear_worker_e2e_client_unavailable(db, worker_id: str) -> None:
    wid = str(worker_id or "").strip()
    if not wid or db is None:
        return
    _ensure_worker_e2e_client_column(db)
    db.execute("UPDATE workers SET e2e_client_unavailable = 0 WHERE id = ?", (wid,))
    db.commit()


def is_worker_e2e_client_unavailable(db, worker_id: str) -> bool:
    wid = str(worker_id or "").strip()
    if not wid or db is None:
        return False
    _ensure_worker_e2e_client_column(db)
    try:
        row = db.execute(
            "SELECT e2e_client_unavailable FROM workers WHERE id = ? AND deleted_at IS NULL",
            (wid,),
        ).fetchone()
        if not row:
            return False
        value = row[0] if isinstance(row, tuple) else row["e2e_client_unavailable"]
        return int(value or 0) == 1
    except Exception:
        return False


def track_worker_e2e_client_header(db, worker_id: str) -> None:
    from flask import request

    hdr = str(request.headers.get("X-E2E-Client-Unavailable") or "").strip().lower()
    if hdr in {"1", "true", "yes"}:
        set_worker_e2e_client_unavailable(db, worker_id)


def company_chat_e2e_keys_ready(db, company_id: str, worker_id: str | None = None) -> bool:
    """True when admin + worker public keys exist so client E2E can work."""
    cid = str(company_id or "").strip()
    if not cid or db is None:
        return False
    from .e2e_identity import E2EIdentityService

    keys = E2EIdentityService(db).list_company_chat_keys(cid, worker_id=worker_id)
    has_user = any(str(k.get("entityType") or "").lower() == "user" for k in keys)
    if not worker_id:
        return has_user
    wid = str(worker_id or "").strip()
    has_worker = any(
        str(k.get("entityType") or "").lower() == "worker"
        and str(k.get("entityId") or "") == wid
        for k in keys
    )
    return has_user and has_worker


def is_e2e_chat_required(db, company_id: str, worker_id: str | None = None) -> bool:
    overrides = company_e2e_settings(db, company_id)
    if overrides.get("e2e_chat_enabled") is False:
        return False
    policy_on = True if overrides.get("e2e_chat_enabled") is True else e2e_chat_required()
    if not policy_on:
        return False
    wid = str(worker_id or "").strip()
    if wid and is_worker_e2e_client_unavailable(db, wid):
        return False
    # Enforce client E2E only when both sides have registered keys (no chicken-and-egg).
    return company_chat_e2e_keys_ready(db, company_id, worker_id=worker_id)


def is_e2e_attachment_required(db, company_id: str, worker_id: str | None = None) -> bool:
    overrides = company_e2e_settings(db, company_id)
    if overrides.get("e2e_attachments_required") is False:
        return False
    policy_on = True if overrides.get("e2e_attachments_required") is True else e2e_attachments_required()
    if not policy_on:
        return False
    wid = str(worker_id or "").strip()
    if wid and is_worker_e2e_client_unavailable(db, wid):
        return False
    return company_chat_e2e_keys_ready(db, company_id, worker_id=worker_id)


def is_e2e_sensitive_required(db, company_id: str) -> bool:
    overrides = company_e2e_settings(db, company_id)
    if overrides.get("e2e_sensitive_required") is False:
        return False
    if overrides.get("e2e_sensitive_required") is True:
        return True
    return e2e_sensitive_fields_required()
