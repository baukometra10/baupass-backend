"""External signature pad / tablet bridge → worker compliance signature."""
from __future__ import annotations

import os
import secrets
from typing import Any


def authorize_device_signature_request(request, db) -> tuple[dict[str, Any] | None, str | None, int | None]:
    """
    Returns (actor_dict, company_id_scope, error_http_code) or (actor, company_id, None) on success.
  company_id_scope None = superadmin all companies.
    """
    from werkzeug.security import check_password_hash

    from backend.server import clean_id_input

    bridge_expected = (os.getenv("BAUPASS_SIGNATURE_BRIDGE_TOKEN") or "").strip()
    bridge_token = (request.headers.get("X-SUPPIX-Signature-Token") or "").strip()
    if bridge_expected and bridge_token and secrets.compare_digest(bridge_expected, bridge_token):
        company_id = clean_id_input(request.headers.get("X-SUPPIX-Company-Id") or "")
        return (
            {"role": "device-bridge", "id": "signature-bridge", "company_id": company_id or None},
            company_id or None,
            None,
        )

    raw_key = (request.headers.get("X-Device-API-Key") or "").strip()
    if raw_key:
        devices = db.execute("SELECT * FROM devices WHERE COALESCE(api_key_hash, '') != ''").fetchall()
        for dev in devices:
            if check_password_hash(dev["api_key_hash"], raw_key):
                return (
                    {"role": "device", "id": str(dev["id"]), "company_id": str(dev["company_id"])},
                    str(dev["company_id"]),
                    None,
                )
        return None, None, 401

    from flask import g

    user = getattr(g, "current_user", None)
    if user and str(user.get("role") or "") in {"superadmin", "company-admin"}:
        cid = str(user.get("company_id") or "").strip() or None
        if user.get("role") == "superadmin":
            cid = None
        return user, cid, None

    return None, None, 401
