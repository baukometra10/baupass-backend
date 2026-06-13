"""
SAP / Oracle integration adapters (health + export preview when configured).
"""
from __future__ import annotations

import os
from typing import Any
from urllib import request as urlrequest


def _probe_url(url: str, headers: dict[str, str] | None = None, timeout: int = 8) -> dict[str, Any]:
    if not url:
        return {"ok": False, "error": "missing_base_url"}
    try:
        req = urlrequest.Request(url, headers=headers or {}, method="GET")
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            return {"ok": 200 <= resp.status < 400, "status": resp.status}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def sap_health(config: dict[str, Any]) -> dict[str, Any]:
    base = str(config.get("base_url") or os.getenv("BAUPASS_SAP_BASE_URL", "")).strip()
    if not base:
        return {
            "ok": False,
            "provider": "sap",
            "probe": "config_required",
            "hint": "Set base_url in integration config or BAUPASS_SAP_BASE_URL",
        }
    token = str(config.get("access_token") or "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    ping = _probe_url(base.rstrip("/") + "/$metadata", headers)
    return {"ok": ping.get("ok"), "provider": "sap", "baseUrl": base, "connectivity": ping}


def oracle_health(config: dict[str, Any]) -> dict[str, Any]:
    base = str(config.get("base_url") or os.getenv("BAUPASS_ORACLE_BASE_URL", "")).strip()
    if not base:
        return {
            "ok": False,
            "provider": "oracle",
            "probe": "config_required",
            "hint": "Set base_url in integration config or BAUPASS_ORACLE_BASE_URL",
        }
    token = str(config.get("access_token") or "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    ping = _probe_url(base.rstrip("/"), headers)
    return {"ok": ping.get("ok"), "provider": "oracle", "baseUrl": base, "connectivity": ping}


def sap_export_preview(db, company_id: int, *, period: str = "") -> dict[str, Any]:
    from .payroll_adapter import payroll_export_preview

    base = payroll_export_preview(db, company_id, period=period)
    return {
        "ok": True,
        "provider": "sap",
        "format": "sap_timesheet_v1",
        "period": base.get("period"),
        "rows": base.get("rows", []),
        "mapping": {"workerId": "PERNR", "access_events": "CATS_QUANTITY"},
    }


def oracle_export_preview(db, company_id: int, *, period: str = "") -> dict[str, Any]:
    from .payroll_adapter import payroll_export_preview

    base = payroll_export_preview(db, company_id, period=period)
    return {
        "ok": True,
        "provider": "oracle",
        "format": "oracle_labor_v1",
        "period": base.get("period"),
        "rows": base.get("rows", []),
        "mapping": {"workerId": "PERSON_ID", "access_events": "HOURS"},
    }


def _erp_export_path(config: dict[str, Any], provider: str) -> str:
    custom = str(config.get("export_path") or "").strip()
    if custom:
        return custom if custom.startswith("/") else f"/{custom}"
    defaults = {
        "sap": "/baupass/timesheet/import",
        "oracle": "/baupass/labor/import",
    }
    return defaults.get(provider, "/baupass/export")


def push_erp_export(
    db,
    company_id: int,
    provider: str,
    config: dict[str, Any],
    *,
    period: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Push payroll/timesheet export to configured SAP or Oracle endpoint."""
    import json

    provider = str(provider or "").strip().lower()
    if provider == "sap":
        preview = sap_export_preview(db, company_id, period=period)
    elif provider == "oracle":
        preview = oracle_export_preview(db, company_id, period=period)
    else:
        return {"ok": False, "error": "unknown_provider", "provider": provider}

    base = str(config.get("base_url") or "").strip()
    if provider == "sap" and not base:
        base = str(os.getenv("BAUPASS_SAP_BASE_URL", "")).strip()
    if provider == "oracle" and not base:
        base = str(os.getenv("BAUPASS_ORACLE_BASE_URL", "")).strip()
    token = str(config.get("access_token") or config.get("api_token") or "").strip()
    if not base:
        return {
            "ok": False,
            "error": "missing_base_url",
            "provider": provider,
            "preview": preview,
            "hint": "Set base_url in integration config",
        }
    if dry_run:
        return {
            "ok": True,
            "dryRun": True,
            "provider": provider,
            "targetUrl": base.rstrip("/") + _erp_export_path(config, provider),
            "rowCount": len(preview.get("rows") or []),
            "preview": preview,
        }

    payload = json.dumps(
        {
            "format": preview.get("format"),
            "period": preview.get("period"),
            "rows": preview.get("rows") or [],
            "mapping": preview.get("mapping") or {},
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = base.rstrip("/") + _erp_export_path(config, provider)
    try:
        req = urlrequest.Request(url, data=payload, headers=headers, method="POST")
        with urlrequest.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:4000]
            return {
                "ok": 200 <= resp.status < 300,
                "provider": provider,
                "status": resp.status,
                "targetUrl": url,
                "rowCount": len(preview.get("rows") or []),
                "responsePreview": body,
            }
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "targetUrl": url,
            "rowCount": len(preview.get("rows") or []),
            "error": str(exc),
            "preview": preview,
        }
