"""Platform health probes for dashboard and guardian."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from flask import Flask

from backend.app.database import get_database_health

_UI_PROBE_PATHS = (
    ("api", "/api/health/live"),
    ("ready", "/api/health/ready"),
    ("admin_v2", "/admin-v2/index.html?embed=1"),
    ("enterprise_hub", "/enterprise-hub.html?embed=1"),
    ("ops_center", "/ops-command-center.html?embed=1"),
)


def collect_platform_health(
    app: Flask,
    *,
    host: str = "",
    public_url: str = "",
) -> dict[str, Any]:
    """Run embed + DB probes without an HTTP round-trip."""
    probes: list[dict[str, Any]] = []
    overall = "ok"
    with app.test_client() as client:
        for key, path in _UI_PROBE_PATHS:
            started = time.monotonic()
            try:
                response = client.get(path, headers={"Accept": "text/html,application/json"})
                ok = response.status_code < 400
                detail = f"HTTP {response.status_code}"
            except Exception as exc:
                ok = False
                detail = str(exc)[:120]
            latency_ms = int((time.monotonic() - started) * 1000)
            if not ok:
                overall = "degraded" if overall == "ok" else overall
                if key in ("api", "ready"):
                    overall = "down"
            probes.append(
                {
                    "id": key,
                    "path": path,
                    "ok": ok,
                    "latencyMs": latency_ms,
                    "detail": detail,
                }
            )

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
    }
