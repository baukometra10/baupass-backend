"""
Integration sync — Microsoft Graph / Google Directory (token-based).
"""
from __future__ import annotations

import json
import time
from typing import Any
from urllib import request as urlrequest


def _http_json(url: str, headers: dict[str, str], timeout: int = 12) -> dict[str, Any]:
    req = urlrequest.Request(url, headers=headers, method="GET")
    started = time.monotonic()
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
    data = json.loads(body or "{}")
    data["_duration_ms"] = int((time.monotonic() - started) * 1000)
    return data


def sync_microsoft365(config: dict[str, str]) -> dict[str, Any]:
    token = str(config.get("access_token") or config.get("graph_access_token") or "").strip()
    if not token:
        return {"ok": False, "error": "missing_access_token", "hint": "Set access_token in integration config"}
    try:
        me = _http_json(
            "https://graph.microsoft.com/v1.0/me",
            {"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        users = _http_json(
            "https://graph.microsoft.com/v1.0/users?$top=5&$select=id,displayName,userPrincipalName",
            {"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        sample = users.get("value") or []
        return {
            "ok": True,
            "provider": "microsoft365",
            "account": me.get("userPrincipalName") or me.get("mail"),
            "usersSampled": len(sample),
            "usersPreview": [
                {"id": u.get("id"), "name": u.get("displayName"), "upn": u.get("userPrincipalName")}
                for u in sample[:5]
            ],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "provider": "microsoft365"}


def sync_google_workspace(config: dict[str, str]) -> dict[str, Any]:
    token = str(config.get("access_token") or "").strip()
    if not token:
        return {"ok": False, "error": "missing_access_token", "hint": "Set access_token in integration config"}
    try:
        profile = _http_json(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            {"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        return {
            "ok": True,
            "provider": "google_workspace",
            "account": profile.get("email"),
            "name": profile.get("name"),
            "sub": profile.get("sub"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "provider": "google_workspace"}


def sync_payroll(config: dict[str, str], company_id: int | None = None) -> dict[str, Any]:
    from .integrations import provider_connectivity

    probe = provider_connectivity("payroll", config)
    if not probe.get("ok"):
        return {"ok": False, "provider": "payroll", "probe": probe}
    if company_id is None:
        return {"ok": True, "provider": "payroll", "probe": probe}
    try:
        from backend.server import get_db
        from .payroll_adapter import payroll_export_preview

        preview = payroll_export_preview(get_db(), str(company_id))
        return {"ok": True, "provider": "payroll", "probe": probe, "exportPreview": preview}
    except Exception as exc:
        return {"ok": True, "provider": "payroll", "probe": probe, "exportPreviewError": str(exc)}


def sync_provider(provider: str, config: dict[str, str], *, company_id: str | int | None = None) -> dict[str, Any]:
    provider = (provider or "").strip().lower()
    if provider == "microsoft365":
        return sync_microsoft365(config)
    if provider == "google_workspace":
        return sync_google_workspace(config)
    if provider == "payroll":
        return sync_payroll(config, company_id=company_id)
    if provider == "sap":
        from .integrations import provider_connectivity
        from .erp_adapters import sap_export_preview

        probe = provider_connectivity(provider, config)
        preview = None
        if company_id is not None:
            try:
                from backend.server import get_db

                preview = sap_export_preview(get_db(), str(company_id))
            except Exception as exc:
                preview = {"error": str(exc)}
        return {"ok": bool(probe.get("ok")), "provider": provider, "probe": probe, "exportPreview": preview}

    if provider == "oracle":
        from .integrations import provider_connectivity
        from .erp_adapters import oracle_export_preview

        probe = provider_connectivity(provider, config)
        preview = None
        if company_id is not None:
            try:
                from backend.server import get_db

                preview = oracle_export_preview(get_db(), str(company_id))
            except Exception as exc:
                preview = {"error": str(exc)}
        return {"ok": bool(probe.get("ok")), "provider": provider, "probe": probe, "exportPreview": preview}
    from .integrations import provider_connectivity

    probe = provider_connectivity(provider, config)
    return {"ok": bool(probe.get("ok")), "provider": provider, "probe": probe}
