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
    from backend.app.platform.security.outbound_url import assert_safe_outbound_url

    safe = assert_safe_outbound_url(base, require_https=True)
    if not safe.get("ok"):
        return {
            "ok": False,
            "error": "unsafe_base_url",
            "detail": safe.get("error"),
            "provider": provider,
            "preview": preview,
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


def sync_erp_delta(
    db,
    company_id: int,
    provider: str,
    config: dict[str, Any],
    *,
    period: str = "",
    since: str = "",
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Delta-oriented ERP sync with idempotency and field-map overrides."""
    import hashlib
    import json
    import time

    provider = str(provider or "").strip().lower()
    mapping = dict(config.get("field_mapping") or {})
    if provider == "sap":
        preview = sap_export_preview(db, company_id, period=period)
        default_map = {"workerId": "PERNR", "access_events": "CATS_QUANTITY"}
    elif provider == "oracle":
        preview = oracle_export_preview(db, company_id, period=period)
        default_map = {"workerId": "PERSON_ID", "access_events": "HOURS"}
    else:
        return {"ok": False, "error": "unknown_provider"}
    field_map = {**default_map, **mapping}
    rows = list(preview.get("rows") or [])
    if since:
        rows = [r for r in rows if str(r.get("updatedAt") or r.get("day") or "") >= since]

    key = str(idempotency_key or "").strip()
    if not key:
        # Hash row *content* so identical payloads replay; changed rows get a new key.
        try:
            canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            canonical = str(rows)
        digest = hashlib.sha256(
            f"{provider}:{company_id}:{period}:{since}:{canonical}".encode("utf-8")
        ).hexdigest()[:32]
        key = f"erp-{provider}-{digest}"

    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS erp_sync_runs (
                idempotency_key TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                status TEXT NOT NULL,
                row_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        existing = db.execute(
            "SELECT status, row_count FROM erp_sync_runs WHERE idempotency_key = ?",
            (key,),
        ).fetchone()
        if existing:
            return {
                "ok": True,
                "idempotentReplay": True,
                "idempotencyKey": key,
                "status": existing["status"],
                "rowCount": existing["row_count"],
            }
    except Exception:
        pass

    push = push_erp_export(
        db,
        company_id,
        provider,
        {**config, "field_mapping": field_map},
        period=period,
        dry_run=bool(config.get("dry_run")),
    )
    status = "ok" if push.get("ok") else "error"
    try:
        db.execute(
            """
            INSERT INTO erp_sync_runs (idempotency_key, company_id, provider, status, row_count, created_at, detail_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                str(company_id),
                provider,
                status,
                int(push.get("rowCount") or len(rows)),
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                json.dumps(
                    {
                        "fieldMap": field_map,
                        "push": {k: push.get(k) for k in ("ok", "error", "status", "targetUrl")},
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        db.commit()
    except Exception:
        pass
    return {
        "ok": bool(push.get("ok")),
        "idempotencyKey": key,
        "provider": provider,
        "fieldMap": field_map,
        "rowCount": len(rows),
        "push": push,
    }
