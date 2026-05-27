"""
Integration provider adapters (lightweight connectivity + status checks).
"""
from __future__ import annotations

import json
import time
from urllib import request as urlrequest


def _request_json(url: str, timeout: int = 8, headers: dict[str, str] | None = None) -> dict:
    req = urlrequest.Request(url, headers=headers or {}, method="GET")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
    try:
        return json.loads(body or "{}")
    except Exception:
        return {"raw": body[:2000]}


def provider_connectivity(provider: str, config: dict[str, str] | None = None) -> dict:
    """
    Validate minimal provider connectivity.
    Returns status payload (no secrets).
    """
    cfg = config or {}
    started = time.monotonic()
    provider = (provider or "").strip().lower()

    # Minimal, safe probes only.
    if provider == "microsoft365":
        tenant = str(cfg.get("tenant_id", "")).strip()
        if not tenant:
            return {"ok": False, "error": "missing_tenant_id"}
        data = _request_json(
            f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
        )
        return {"ok": "authorization_endpoint" in data, "probe": "openid_config"}

    if provider == "google_workspace":
        data = _request_json("https://accounts.google.com/.well-known/openid-configuration")
        return {"ok": "authorization_endpoint" in data, "probe": "openid_config"}

    if provider in {"payroll", "sap", "oracle"}:
        # Placeholder adapters with explicit state so ops can track readiness.
        return {"ok": True, "probe": "adapter_stub", "note": "provider adapter scaffold active"}

    return {"ok": False, "error": "unknown_provider"}
