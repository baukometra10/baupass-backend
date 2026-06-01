"""
BauPass – Health Check Routes (نموذج على blueprint)
=====================================================
مثال على أول route منقول من server.py إلى Architecture الجديدة.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from flask import current_app, jsonify, request

from . import health_bp
from backend.app.database import get_database_health
from backend.app.tasks import get_dead_letter_stats, get_queue_stats, get_worker_heartbeat_stats


@health_bp.get("/health")
def api_health():
    """
    Health check شامل:
    - حالة قاعدة البيانات
    - حالة Redis
    - حالة Task Queues
    - Uptime
    """
    start = time.monotonic()
    status = "ok"
    checks = {}

    # ── Database Check ────────────────────────────────────────────────────────
    db_health = get_database_health()
    checks["database"] = db_health
    if db_health.get("status") != "ok":
        status = "degraded"

    # ── Redis Check ───────────────────────────────────────────────────────────
    try:
        from backend.app.extensions import get_redis
        redis = get_redis()
        if redis:
            redis.ping()
            checks["redis"] = {"status": "ok"}
        else:
            checks["redis"] = {"status": "unavailable", "note": "Rate limiting degraded to in-memory"}
    except Exception as exc:
        checks["redis"] = {"status": "error", "error": str(exc)}

    # ── Task Queue Check ──────────────────────────────────────────────────────
    try:
        queue_stats = get_queue_stats()
        checks["queues"] = {"status": "ok", "stats": queue_stats}
    except Exception:
        checks["queues"] = {"status": "unavailable"}

    # ── Dead Letter Queue Check ──────────────────────────────────────────────
    try:
        checks["dead_letter"] = get_dead_letter_stats()
    except Exception:
        checks["dead_letter"] = {"status": "unavailable"}

    # ── Worker Heartbeat Check ───────────────────────────────────────────────
    try:
        workers = get_worker_heartbeat_stats()
        checks["workers"] = workers

        rq_modes_enabled = any(
            str(os.getenv(name, "thread")).strip().lower() == "rq"
            for name in (
                "BAUPASS_INVOICE_RETRY_MODE",
                "BAUPASS_WORKER_SESSION_CLEANUP_MODE",
                "BAUPASS_DAILY_JOBS_MODE",
            )
        )
        if rq_modes_enabled and int(workers.get("active", 0)) < 1:
            status = "degraded"
    except Exception:
        checks["workers"] = {"status": "unavailable"}
        status = "degraded"

    # ── Response ──────────────────────────────────────────────────────────────
    duration_ms = int((time.monotonic() - start) * 1000)

    return jsonify({
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_ms": duration_ms,
        "checks": checks,
    }), 200 if status == "ok" else 503


@health_bp.get("/health/ready")
def readiness():
    """Kubernetes readiness probe — يتحقق أن التطبيق جاهز لاستقبال الطلبات."""
    db_health = get_database_health()
    if db_health.get("status") == "ok":
        return jsonify({"ready": True}), 200
    return jsonify({"ready": False, "error": db_health.get("error", "database_unhealthy")}), 503


@health_bp.get("/health/live")
def liveness():
    """Kubernetes liveness probe — يتحقق أن العملية حية."""
    return jsonify({"alive": True}), 200


_UI_PROBE_PATHS = (
    ("api", "/api/health/live"),
    ("ready", "/api/health/ready"),
    ("admin_v2", "/admin-v2/index.html?embed=1"),
    ("enterprise_hub", "/enterprise-hub.html?embed=1"),
    ("ops_center", "/ops-command-center.html?embed=1"),
)


@health_bp.get("/health/platform")
def platform_health():
    """Embed + Railway readiness for Control Pass dashboard."""
    probes = []
    overall = "ok"
    with current_app.test_client() as client:
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

    db_health = get_database_health()
    ready = db_health.get("status") == "ok"
    if not ready:
        overall = "degraded" if overall != "down" else overall

    host = (request.host or "").strip()
    cloud = {
        "provider": "railway" if host.endswith(".up.railway.app") else "self-hosted",
        "host": host,
        "publicUrl": (os.getenv("PUBLIC_BASE_URL") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip()
        or request.url_root.rstrip("/"),
    }

    return jsonify(
        {
            "status": overall,
            "ready": ready,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cloud": cloud,
            "database": db_health,
            "probes": probes,
        }
    ), 200 if overall == "ok" else 503


@health_bp.get("/health/queues")
def queue_health():
    """Queue-focused health endpoint for operations dashboards."""
    return jsonify(
        {
            "queues": get_queue_stats(),
            "dead_letter": get_dead_letter_stats(),
            "workers": get_worker_heartbeat_stats(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    ), 200
