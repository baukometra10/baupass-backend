"""Background job run status in Redis — used by /api/health and setup-status."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

STATUS_KEY_PREFIX = "baupass:job:status:"
STATUS_TTL_SECONDS = max(86400, int(os.getenv("BAUPASS_JOB_STATUS_TTL_SECONDS", "604800")))

RQ_JOB_MODE_VARS: tuple[tuple[str, str], ...] = (
    ("invoice_retry", "BAUPASS_INVOICE_RETRY_MODE"),
    ("worker_session_cleanup", "BAUPASS_WORKER_SESSION_CLEANUP_MODE"),
    ("daily_jobs", "BAUPASS_DAILY_JOBS_MODE"),
    ("dunning", "BAUPASS_DUNNING_MODE"),
    ("ai_briefing", "BAUPASS_AI_BRIEFING_MODE"),
)

TRACKED_COMPONENTS: tuple[str, ...] = (
    "imap_poller",
    "daily_jobs",
    "dunning",
    "invoice_retry",
    "worker_session_cleanup",
    "ai_briefing",
)


def _redis_conn():
    from backend.app.tasks import _redis_conn

    return _redis_conn


def get_rq_mode_summary() -> dict[str, str]:
    return {name: str(os.getenv(env_var, "thread")).strip().lower() for name, env_var in RQ_JOB_MODE_VARS}


def record_job_run(
    component: str,
    *,
    ok: bool,
    details: dict | None = None,
    error: str | None = None,
) -> None:
    conn = _redis_conn()
    if conn is None:
        return

    now = datetime.now(timezone.utc).isoformat()
    key = STATUS_KEY_PREFIX + str(component)
    prev: dict[str, Any] = {}
    consecutive_failures = 0

    try:
        prev_raw = conn.get(key)
        if prev_raw:
            prev = json.loads(prev_raw.decode() if isinstance(prev_raw, (bytes, bytearray)) else prev_raw)
            consecutive_failures = int(prev.get("consecutiveFailures") or 0)
    except Exception:
        prev = {}

    if ok:
        consecutive_failures = 0
    else:
        consecutive_failures += 1

    payload = {
        "component": str(component),
        "ok": bool(ok),
        "lastRunAt": now,
        "lastSuccessAt": now if ok else str(prev.get("lastSuccessAt") or ""),
        "lastErrorAt": now if not ok else str(prev.get("lastErrorAt") or ""),
        "consecutiveFailures": consecutive_failures,
        "error": str(error or "") if not ok else "",
        "details": details or {},
    }

    try:
        conn.setex(key, STATUS_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


def get_job_status(component: str) -> dict[str, Any]:
    conn = _redis_conn()
    if conn is None:
        return {"status": "unavailable", "reason": "redis_not_initialized"}

    try:
        raw = conn.get(STATUS_KEY_PREFIX + str(component))
        if not raw:
            return {"status": "unknown", "component": component}
        data = json.loads(raw.decode() if isinstance(raw, (bytes, bytearray)) else raw)
        data["status"] = "ok" if data.get("ok") else "error"
        return data
    except Exception as exc:
        return {"status": "error", "component": component, "error": str(exc)}


def collect_background_jobs_health() -> dict[str, Any]:
    from backend.app.tasks import get_queue_stats, get_worker_heartbeat_stats, task_queues_ready

    rq_modes = get_rq_mode_summary()
    any_rq = any(mode == "rq" for mode in rq_modes.values())
    workers = get_worker_heartbeat_stats()
    jobs = {name: get_job_status(name) for name in TRACKED_COMPONENTS}

    degraded: list[str] = []
    if any_rq and int(workers.get("active") or 0) < 1:
        degraded.append("rq_worker_missing")
    for name, snapshot in jobs.items():
        if int(snapshot.get("consecutiveFailures") or 0) >= 3:
            degraded.append(f"{name}_failing")

    return {
        "queuesReady": task_queues_ready(),
        "rqModes": rq_modes,
        "anyRqMode": any_rq,
        "workers": workers,
        "queues": get_queue_stats() if task_queues_ready() else {},
        "jobs": jobs,
        "degraded": degraded,
        "healthy": len(degraded) == 0,
    }
