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
    return dict(row)
