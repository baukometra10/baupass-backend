"""
OAuth token helpers for integration_connections.config_json (encrypted at rest).
"""
from __future__ import annotations

import json
import time
from typing import Any

from backend.app.platform.security.field_encryption import encrypt_text, decrypt_text


def merge_oauth_config(existing: dict[str, Any], tokens: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(existing or {})
    oauth = dict(cfg.get("oauth") or {})
    for key in ("access_token", "refresh_token", "expires_at", "token_type", "scope"):
        if key in tokens and tokens[key]:
            if key in {"access_token", "refresh_token"}:
                oauth[key] = encrypt_text(str(tokens[key]))
            else:
                oauth[key] = tokens[key]
    oauth["updated_at"] = int(time.time())
    cfg["oauth"] = oauth
    return cfg


def extract_oauth_config(config: dict[str, Any]) -> dict[str, Any]:
    oauth = dict((config or {}).get("oauth") or {})
    out: dict[str, Any] = {}
    for key, value in oauth.items():
        if key in {"access_token", "refresh_token"} and value:
            try:
                out[key] = decrypt_text(str(value))
            except Exception:
                out[key] = str(value)
        else:
            out[key] = value
    return out


def oauth_config_for_api(config: dict[str, Any]) -> dict[str, Any]:
    """Mask secrets for API responses."""
    oauth = extract_oauth_config(config)
    masked = {}
    for key, value in oauth.items():
        if key in {"access_token", "refresh_token"} and value:
            masked[key] = "***" + str(value)[-4:] if len(str(value)) > 4 else "***"
        else:
            masked[key] = value
    return masked
