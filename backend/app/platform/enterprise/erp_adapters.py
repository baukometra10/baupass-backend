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
