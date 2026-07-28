"""Platform health probes for dashboard and guardian."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask

from backend.app.database import get_database_health

_UI_PROBE_PATHS = (
    ("api", "/api/health/live"),
    ("ready", "/api/health/ready"),
    ("worker_app", "/emp-app.html"),
    ("admin_v2", "/admin-v2/index.html?embed=1"),
    ("enterprise_hub", "/enterprise-hub.html?embed=1"),
    ("ops_center", "/ops-command-center.html?embed=1"),
)

# Auth may return 401/403 — that still proves the route is mounted and responding.
_API_PROBE_PATHS = (
    ("api_companies", "/api/companies"),
    ("api_ops_command", "/api/ops-os/command-center"),
    ("api_daily_brief", "/api/ops-os/daily-brief"),
    ("api_live_map", "/api/ops-os/live-map"),
    ("api_docs_inbox", "/api/documents/inbox"),
    ("api_admin_overview", "/api/v2/admin/overview"),
    ("api_billing_pricing", "/api/v2/billing/pricing"),
)


def _probe_http(client, *, probe_id: str, path: str, critical: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    try:
        response = client.get(path, headers={"Accept": "text/html,application/json"})
        # <500 means the stack answered (incl. auth gates). 5xx / exceptions = broken.
        ok = int(response.status_code) < 500
        detail = f"HTTP {response.status_code}"
    except Exception as exc:
        ok = False
        detail = str(exc)[:120]
    return {
        "id": probe_id,
        "path": path,
        "ok": ok,
        "critical": critical,
        "latencyMs": int((time.monotonic() - started) * 1000),
        "detail": detail,
    }


def collect_platform_health(
    app: Flask,
    *,
    host: str = "",
    public_url: str = "",
) -> dict[str, Any]:
    """Run embed + critical API + DB probes without an HTTP round-trip."""
    probes: list[dict[str, Any]] = []
    overall = "ok"
    with app.test_client() as client:
        for key, path in _UI_PROBE_PATHS:
            probe = _probe_http(client, probe_id=key, path=path, critical=key in ("api", "ready"))
            if not probe["ok"]:
                overall = "degraded" if overall == "ok" else overall
                if probe.get("critical"):
                    overall = "down"
            probes.append(probe)

        for key, path in _API_PROBE_PATHS:
            probe = _probe_http(client, probe_id=key, path=path, critical=True)
            if not probe["ok"]:
                if overall != "down":
                    overall = "degraded"
            probes.append(probe)

    with app.app_context():
        try:
            from backend.app.health.readiness import _database_status
            from backend.server import DB_PATH

            db_health = _database_status(Path(DB_PATH))
        except Exception:
            db_health = get_database_health()
    ready = bool(db_health.get("ok"))
    if not ready:
        overall = "degraded" if overall != "down" else overall

    # Route registration probe (no HTTP) — missing mounts are silent customer killers.
    route_probe: dict[str, Any] = {"ok": True, "missing": []}
    try:
        from backend.app.health.route_probe import build_api_route_probe
        from backend.server import _route_methods_for

        route_probe = build_api_route_probe(_route_methods_for)
        if not route_probe.get("ok"):
            overall = "degraded" if overall != "down" else overall
            missing = route_probe.get("missing") or []
            probes.append(
                {
                    "id": "api_route_registry",
                    "path": "route_registry",
                    "ok": False,
                    "critical": True,
                    "latencyMs": 0,
                    "detail": f"missing {len(missing)} critical route(s)",
                    "missing": missing[:8],
                }
            )
        else:
            probes.append(
                {
                    "id": "api_route_registry",
                    "path": "route_registry",
                    "ok": True,
                    "critical": True,
                    "latencyMs": 0,
                    "detail": "all critical routes registered",
                }
            )
    except Exception as exc:
        probes.append(
            {
                "id": "api_route_registry",
                "path": "route_registry",
                "ok": False,
                "critical": True,
                "latencyMs": 0,
                "detail": str(exc)[:120],
            }
        )
        overall = "degraded" if overall != "down" else overall

    host = (host or "").strip()
    if not public_url:
        public_url = (
            (os.getenv("PUBLIC_BASE_URL") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip()
        )

    return {
        "status": overall,
        "ready": ready,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cloud": {
            "provider": "railway" if host.endswith(".up.railway.app") else "self-hosted",
            "host": host,
            "publicUrl": public_url,
        },
        "database": db_health,
        "probes": probes,
        "routeProbe": route_probe,
    }
