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
from backend.app.tasks.job_health import collect_background_jobs_health, get_rq_mode_summary


def _apply_rq_worker_degradation(checks: dict, status: str) -> str:
    """Mark health degraded when any job mode uses RQ but no worker heartbeat is active."""
    rq_modes = get_rq_mode_summary()
    checks["rqModes"] = rq_modes
    any_rq = any(mode == "rq" for mode in rq_modes.values())
    workers = checks.get("workers") or {}
    if any_rq and int(workers.get("active") or 0) < 1:
        return "degraded"
    return status


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
        status = _apply_rq_worker_degradation(checks, status)
    except Exception:
        checks["workers"] = {"status": "unavailable"}
        status = "degraded"

    # ── Background job snapshots (IMAP, daily, dunning, …) ─────────────────
    try:
        bg_jobs = collect_background_jobs_health()
        checks["backgroundJobs"] = bg_jobs
        if bg_jobs.get("degraded"):
            status = "degraded"
    except Exception as exc:
        checks["backgroundJobs"] = {"status": "unavailable", "error": str(exc)}

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
    """Kubernetes readiness probe — DB + optional RQ worker when rq modes are enabled."""
    db_health = get_database_health()
    if db_health.get("status") != "ok":
        return jsonify({"ready": False, "error": db_health.get("error", "database_unhealthy")}), 503

    try:
        bg_jobs = collect_background_jobs_health()
        if bg_jobs.get("anyRqMode") and int((bg_jobs.get("workers") or {}).get("active") or 0) < 1:
            return jsonify(
                {
                    "ready": False,
                    "error": "rq_worker_missing",
                    "rqModes": bg_jobs.get("rqModes"),
                }
            ), 503
    except Exception:
        pass

    return jsonify({"ready": True}), 200


@health_bp.get("/health/live")
def liveness():
    """Kubernetes liveness probe — يتحقق أن العملية حية."""
    return jsonify({"alive": True}), 200


@health_bp.get("/health/platform")
def platform_health():
    """Embed + Railway readiness for SUPPIX dashboard."""
    from backend.app.health.platform_probe import collect_platform_health

    host = (request.host or "").strip()
    payload = collect_platform_health(current_app._get_current_object(), host=host, public_url=request.url_root.rstrip("/"))
    overall = str(payload.get("status") or "ok").lower()
    return jsonify(payload), 200 if overall in ("ok", "degraded") else 503


@health_bp.get("/health/queues")
def queue_health():
    """Queue-focused health endpoint for operations dashboards."""
    bg_jobs = collect_background_jobs_health()
    return jsonify(
        {
            "queues": get_queue_stats(),
            "dead_letter": get_dead_letter_stats(),
            "workers": get_worker_heartbeat_stats(),
            "backgroundJobs": bg_jobs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    ), 200
