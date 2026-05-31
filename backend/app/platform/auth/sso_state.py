"""SSO OAuth/SAML state — Redis when available, in-memory fallback."""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from typing import Any

logger = logging.getLogger("baupass.auth.sso_state")

_TTL_SEC = int(os.getenv("BAUPASS_SSO_STATE_TTL_SEC", "600"))
_PREFIX = "baupass:sso:state:"
_MEM: dict[str, tuple[str, float]] = {}


def _redis_enabled() -> bool:
    if os.getenv("BAUPASS_SSO_STATE_REDIS", "").strip().lower() in {"0", "false", "no"}:
        return False
    if os.getenv("BAUPASS_SSO_STATE_REDIS", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return bool(os.getenv("REDIS_URL", "").strip())


def _redis_client():
    if not _redis_enabled():
        return None
    try:
        from backend.app.extensions import get_redis

        return get_redis()
    except Exception:
        return None


def _mem_set(state: str, payload: dict[str, Any]) -> None:
    _MEM[state] = (json.dumps(payload), time.time() + _TTL_SEC)


def _mem_pop(state: str) -> dict[str, Any] | None:
    entry = _MEM.pop(state, None)
    if not entry:
        return None
    raw, expires = entry
    if time.time() > expires:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def store_state(state: str, payload: dict[str, Any]) -> None:
    """Persist CSRF state (OIDC marker or SAML relay data)."""
    if not state:
        return
    r = _redis_client()
    if r is not None:
        try:
            r.setex(f"{_PREFIX}{state}", _TTL_SEC, json.dumps(payload))
            return
        except Exception as exc:
            logger.warning("SSO state Redis set failed, using memory: %s", exc)
    _mem_set(state, payload)


def consume_state(state: str) -> dict[str, Any] | None:
    """Load and delete state (one-time use)."""
    if not state:
        return None
    r = _redis_client()
    if r is not None:
        try:
            key = f"{_PREFIX}{state}"
            pipe = r.pipeline()
            pipe.get(key)
            pipe.delete(key)
            raw, _ = pipe.execute()
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                return json.loads(raw)
        except Exception as exc:
            logger.warning("SSO state Redis consume failed, trying memory: %s", exc)
    return _mem_pop(state)


def issue_oidc_state() -> str:
    """Create random state for OpenID Connect authorize redirect."""
    state = secrets.token_urlsafe(24)
    store_state(state, {"kind": "oidc"})
    return state


def consume_oidc_state(state: str) -> bool:
    payload = consume_state(state)
    return bool(payload and payload.get("kind") == "oidc")


def issue_saml_relay(request_id: str) -> str:
    """Create RelayState token linked to AuthnRequest ID."""
    state = secrets.token_urlsafe(24)
    store_state(state, {"kind": "saml", "req_id": request_id})
    return state


def consume_saml_relay(state: str) -> str | None:
    payload = consume_state(state)
    if not payload or payload.get("kind") != "saml":
        return None
    return str(payload.get("req_id") or "") or None
