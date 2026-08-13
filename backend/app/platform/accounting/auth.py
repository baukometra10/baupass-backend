"""Auth helpers for external accounting app (per-company API key + HMAC)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

API_KEY_PREFIX = "acc_live_"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256((raw_key or "").encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def generate_signing_secret() -> str:
    return secrets.token_urlsafe(32)


def sign_payload(secret: str, *, timestamp: str, body: bytes) -> str:
    msg = f"{timestamp}.".encode("utf-8") + (body or b"")
    return hmac.new((secret or "").encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_signature(
    secret: str,
    *,
    timestamp: str,
    body: bytes,
    signature: str,
    max_skew_seconds: int = 300,
) -> bool:
    if not secret or not signature or not timestamp:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - ts) > max_skew_seconds:
        return False
    expected = sign_payload(secret, timestamp=str(ts), body=body or b"")
    return hmac.compare_digest(expected, str(signature).strip().lower())


def _extract_bearer(raw: str) -> str:
    value = str(raw or "").strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def extract_lohn_api_key_from_headers(headers) -> str:
    """Read accounting / master key from common Lohn + platform header names."""
    get = headers.get if hasattr(headers, "get") else (lambda *_a, **_k: "")
    for name in (
        "X-Accounting-Key",
        "X-WorkPass-Accounting-Key",
        "X-WorkPass-Key",
        "X-WorkPass-Master-Key",
        "X-WorkPass-Webhook-Key",
        "X-Api-Key",
        "X-Platform-Api-Key",
        "Authorization",
    ):
        raw = _extract_bearer(str(get(name) or ""))
        if raw:
            return raw
    return ""


def list_accepted_lohn_platform_keys(db=None) -> list[str]:
    """All shared keys the platform accepts from WorkPass Lohn."""
    import os

    from .platform_link import get_platform_link, resolve_lohn_api_keys, resolve_master_api_keys

    link = get_platform_link(db) if db is not None else {}
    accepted: list[str] = []
    seen: set[str] = set()
    for candidate in (*resolve_lohn_api_keys(link), *resolve_master_api_keys(link)):
        value = str(candidate or "").strip()
        if value and value not in seen:
            seen.add(value)
            accepted.append(value)
    for env_name in (
        "WORKPASS_API_KEY",
        "WORKPASS_PLATFORM_API_KEY",
        "WORKPASS_LOHN_MASTER_KEY",
        "WORKPASS_PLATFORM_WEBHOOK_KEY",
    ):
        value = str(os.environ.get(env_name) or "").strip()
        if value and value not in seen:
            seen.add(value)
            accepted.append(value)
    return accepted


def is_known_lohn_platform_key(db, api_key: str) -> bool:
    key = str(api_key or "").strip()
    if not key:
        return False
    if key.startswith(API_KEY_PREFIX):
        return True
    for candidate in list_accepted_lohn_platform_keys(db):
        if len(candidate) == len(key) and hmac.compare_digest(candidate, key):
            return True
    return False


def extract_explicit_lohn_bridge_credentials(headers, *, query_company: str = "", db=None) -> tuple[str, str]:
    """
    Credentials for shared admin routes (e.g. GET /api/contracts).

    Enter Lohn bridge when:
    - X-WorkPass-Company-Id (+ key headers / Bearer), OR
    - Bearer/X-WorkPass-Key matches a known WORKPASS_* key and company is in header or query.

    Admin session Bearer tokens do not match WORKPASS_* keys, so admin UI stays intact.
    """
    get = headers.get if hasattr(headers, "get") else (lambda *_a, **_k: "")
    company_id = str(
        get("X-WorkPass-Company-Id") or get("X-Company-Id") or query_company or ""
    ).strip()
    key = ""
    for name in (
        "X-Accounting-Key",
        "X-WorkPass-Accounting-Key",
        "X-WorkPass-Key",
        "X-WorkPass-Master-Key",
        "X-WorkPass-Webhook-Key",
        "X-Api-Key",
        "X-Platform-Api-Key",
    ):
        raw = _extract_bearer(str(get(name) or ""))
        if raw:
            key = raw
            break
    if not key:
        key = _extract_bearer(str(get("Authorization") or ""))

    if not key:
        return "", ""

    # Without a company id we cannot scope the pull
    if not company_id:
        # Only claim Lohn mode when key is explicitly a WorkPass header (not bare Authorization)
        has_explicit = any(
            str(get(n) or "").strip()
            for n in (
                "X-WorkPass-Key",
                "X-WorkPass-Company-Id",
                "X-Accounting-Key",
                "X-WorkPass-Accounting-Key",
            )
        )
        return (key, "") if has_explicit else ("", "")

    # If only Authorization + ?company_id (admin UI), require known platform key
    has_company_header = bool(
        str(get("X-WorkPass-Company-Id") or get("X-Company-Id") or "").strip()
    )
    has_explicit_key_header = any(
        str(get(n) or "").strip()
        for n in (
            "X-WorkPass-Key",
            "X-Accounting-Key",
            "X-WorkPass-Accounting-Key",
            "X-Api-Key",
            "X-Platform-Api-Key",
        )
    )
    if has_company_header or has_explicit_key_header:
        return key, company_id
    if db is not None and is_known_lohn_platform_key(db, key):
        return key, company_id
    return "", ""


def authenticate_accounting_request(
    db,
    *,
    company_id: str,
    api_key: str,
    timestamp: str = "",
    signature: str = "",
    body: bytes = b"",
    require_signature: bool = False,
) -> dict[str, Any] | None:
    """Validate company-scoped accounting key. Signature optional unless require_signature."""
    from .schema import ensure_accounting_schema

    ensure_accounting_schema(db)
    company_id = (company_id or "").strip()
    api_key = (api_key or "").strip()
    if not company_id or not api_key.startswith(API_KEY_PREFIX):
        return None
    row = db.execute(
        """
        SELECT id, company_id, enabled, webhook_url, api_key_hash, signing_secret, run_day
        FROM accounting_integrations
        WHERE company_id = ? AND api_key_hash = ? AND enabled = 1
        LIMIT 1
        """,
        (company_id, hash_api_key(api_key)),
    ).fetchone()
    if not row:
        return None
    secret = str(row["signing_secret"] or "")
    if require_signature or signature:
        if not verify_signature(secret, timestamp=timestamp, body=body, signature=signature):
            return None
    out = dict(row)
    out["authMode"] = "company_accounting_key"
    return out


def authenticate_lohn_pull_request(
    db,
    *,
    company_id: str,
    api_key: str,
    timestamp: str = "",
    signature: str = "",
    body: bytes = b"",
    require_signature: bool = False,
) -> dict[str, Any] | None:
    """
    Accept either per-company acc_live_* key OR shared WORKPASS_API_KEY / master key.
    Lohn UI often sends WORKPASS_API_KEY with X-WorkPass-Company-Id.
    """
    from .company_opt_in import is_workpass_lohn_enabled
    from .schema import ensure_accounting_schema

    company_id = (company_id or "").strip()
    api_key = (api_key or "").strip()
    if not company_id or not api_key:
        return None

    integ = authenticate_accounting_request(
        db,
        company_id=company_id,
        api_key=api_key,
        timestamp=timestamp,
        signature=signature,
        body=body,
        require_signature=require_signature,
    )
    if integ:
        return integ

    ensure_accounting_schema(db)
    lohn_enabled = is_workpass_lohn_enabled(db, company_id)

    accepted = list_accepted_lohn_platform_keys(db)

    matched = None
    for k in accepted:
        if len(k) == len(api_key) and hmac.compare_digest(k, api_key):
            matched = k
            break
    if not matched:
        return None
    if not lohn_enabled:
        # Distinguish bad key vs opt-out (routes can map to 403)
        return {
            "id": f"master-{company_id}",
            "company_id": company_id,
            "enabled": 0,
            "webhook_url": "",
            "api_key_hash": "",
            "signing_secret": "",
            "run_day": 1,
            "authMode": "platform_master_key",
            "lohnDisabled": True,
        }

    # Prefer existing integration row when present; otherwise synthetic master auth.
    row = db.execute(
        """
        SELECT id, company_id, enabled, webhook_url, api_key_hash, signing_secret, run_day
        FROM accounting_integrations
        WHERE company_id = ? AND enabled = 1
        LIMIT 1
        """,
        (company_id,),
    ).fetchone()
    if row:
        out = dict(row)
        out["authMode"] = "platform_master_key"
        return out
    return {
        "id": f"master-{company_id}",
        "company_id": company_id,
        "enabled": 1,
        "webhook_url": "",
        "api_key_hash": "",
        "signing_secret": "",
        "run_day": 1,
        "authMode": "platform_master_key",
    }
