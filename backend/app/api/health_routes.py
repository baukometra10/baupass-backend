"""
WorkPass – Health Check Routes (نموذج على blueprint)
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


@health_bp.get("/health/platform")
def platform_health():
    """Embed + Railway readiness for WorkPass dashboard."""
    from backend.app.health.platform_probe import collect_platform_health

    host = (request.host or "").strip()
    payload = collect_platform_health(current_app._get_current_object(), host=host, public_url=request.url_root.rstrip("/"))
    overall = str(payload.get("status") or "ok").lower()
    return jsonify(payload), 200 if overall == "ok" else 503


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
