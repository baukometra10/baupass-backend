from __future__ import annotations

import importlib
import logging
import os
import time
from typing import Any

from . import enqueue_in_deduped, scheduled_job_pending
from .job_health import record_job_run

logger = logging.getLogger("baupass.tasks.legacy")

SCHEDULED_JOB_IDS = {
    "invoice_retry": "baupass:scheduled:legacy.invoice_retry",
    "worker_session_cleanup": "baupass:scheduled:legacy.worker_session_cleanup",
    "daily_jobs": "baupass:scheduled:legacy.daily_jobs",
    "dunning": "baupass:scheduled:legacy.dunning",
}


def _import_legacy_server():
    # Prevent legacy module import from spawning its own background threads.
    os.environ.setdefault("BAUPASS_ENABLE_BACKGROUND_JOBS", "0")
    os.environ.setdefault("BAUPASS_ENABLE_IMAP_POLLER", "0")
    return importlib.import_module("backend.server")


def _record_task_failure_alert(component: str, result: dict[str, Any]) -> None:
    try:
        legacy = _import_legacy_server()
        with legacy.app.app_context():
            legacy.create_system_alert(
                legacy.get_db(),
                code=f"{component}_cycle_failed",
                severity="warning",
                message=f"Hintergrundjob {component} fehlgeschlagen.",
                details=result,
                dedup_minutes=30,
            )
    except Exception:
        logger.exception("Failed to persist system alert for %s", component)


def _finalize_legacy_task(component: str, result: dict[str, Any]) -> dict[str, Any]:
    ok = bool(result.get("ok", True))
    error = str(result.get("error") or "").strip()
    record_job_run(component, ok=ok, details=result, error=error or None)
    if not ok:
        _record_task_failure_alert(component, result)
    return result


def _schedule_next(component: str, interval_seconds: int, task_fn, *, description: str) -> None:
    job_id = SCHEDULED_JOB_IDS[component]
    enqueue_in_deduped(
        interval_seconds,
        "scheduled",
        task_fn,
        job_id=job_id,
        reschedule=True,
        description=description,
    )


def _bootstrap_scheduled_task(
    *,
    component: str,
    lock_key: str,
    lock_ttl_seconds: int,
    delay_seconds: int,
    task_fn,
    description: str,
) -> bool:
    job_id = SCHEDULED_JOB_IDS[component]
    if scheduled_job_pending(job_id):
        logger.info("%s scheduler already has a pending RQ job", component)
        return False

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis

        conn = redis.Redis.from_url(redis_url, decode_responses=True)
        lock_acquired = bool(conn.set(lock_key, str(int(time.time())), nx=True, ex=max(300, lock_ttl_seconds)))
        if not lock_acquired:
            logger.info("%s scheduler bootstrap lock held", component)
            return False

        enqueue_in_deduped(
            delay_seconds,
            "scheduled",
            task_fn,
            job_id=job_id,
            reschedule=True,
            description=description,
        )
        logger.info("%s scheduler bootstrapped via RQ", component)
        return True
    except Exception as exc:
        logger.error("Failed to bootstrap %s scheduler: %s", component, exc)
        return False


def run_invoice_retry_cycle_once_task(*, reschedule: bool = True) -> dict[str, Any]:
    legacy = _import_legacy_server()
    result = _finalize_legacy_task("invoice_retry", legacy.run_invoice_retry_cycle_once())

    if reschedule:
        interval = max(60, int(os.getenv("BAUPASS_INVOICE_RETRY_SECONDS", "180")))
        _schedule_next("invoice_retry", interval, run_invoice_retry_cycle_once_task, description="legacy.invoice_retry.cycle")

    if not result.get("ok", True):
        raise RuntimeError(result.get("error") or "invoice_retry_failed")
    return result


def bootstrap_legacy_invoice_retry_scheduler() -> bool:
    interval = max(60, int(os.getenv("BAUPASS_INVOICE_RETRY_SECONDS", "180")))
    return _bootstrap_scheduled_task(
        component="invoice_retry",
        lock_key="baupass:rq:legacy:invoice_retry:bootstrap",
        lock_ttl_seconds=max(interval * 2, 600),
        delay_seconds=5,
        task_fn=run_invoice_retry_cycle_once_task,
        description="legacy.invoice_retry.bootstrap",
    )


def run_worker_session_cleanup_cycle_once_task(*, reschedule: bool = True) -> dict[str, Any]:
    legacy = _import_legacy_server()
    result = _finalize_legacy_task("worker_session_cleanup", legacy.run_worker_session_cleanup_cycle_once())

    if reschedule:
        interval = max(60, int(os.getenv("BAUPASS_WORKER_SESSION_CLEANUP_SECONDS", "300")))
        _schedule_next(
            "worker_session_cleanup",
            interval,
            run_worker_session_cleanup_cycle_once_task,
            description="legacy.worker_session_cleanup.cycle",
        )

    if not result.get("ok", True):
        raise RuntimeError(result.get("error") or "worker_session_cleanup_failed")
    return result


def bootstrap_legacy_worker_session_cleanup_scheduler() -> bool:
    interval = max(60, int(os.getenv("BAUPASS_WORKER_SESSION_CLEANUP_SECONDS", "300")))
    return _bootstrap_scheduled_task(
        component="worker_session_cleanup",
        lock_key="baupass:rq:legacy:worker_session_cleanup:bootstrap",
        lock_ttl_seconds=max(interval * 2, 600),
        delay_seconds=5,
        task_fn=run_worker_session_cleanup_cycle_once_task,
        description="legacy.worker_session_cleanup.bootstrap",
    )


def run_daily_jobs_cycle_once_task(*, reschedule: bool = True) -> dict[str, Any]:
    legacy = _import_legacy_server()
    result = _finalize_legacy_task("daily_jobs", legacy.run_daily_jobs_cycle_once())

    if reschedule:
        interval = max(3600, int(os.getenv("BAUPASS_DAILY_JOBS_SECONDS", "86400")))
        _schedule_next("daily_jobs", interval, run_daily_jobs_cycle_once_task, description="legacy.daily_jobs.cycle")

    if not result.get("ok", True):
        raise RuntimeError(result.get("error") or "daily_jobs_failed")
    return result


def run_dunning_cycle_once_task(*, reschedule: bool = True) -> dict[str, Any]:
    legacy = _import_legacy_server()
    try:
        with legacy.app.app_context():
            legacy.run_dunning_job_once()
        result = {"ok": True}
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    result = _finalize_legacy_task("dunning", result)

    if reschedule:
        interval_hours = max(1, int(os.getenv("BAUPASS_DUNNING_INTERVAL_HOURS", "24")))
        _schedule_next("dunning", interval_hours * 3600, run_dunning_cycle_once_task, description="legacy.dunning.cycle")

    if not result.get("ok", True):
        raise RuntimeError(result.get("error") or "dunning_failed")
    return result


def bootstrap_legacy_dunning_scheduler() -> bool:
    interval_hours = max(1, int(os.getenv("BAUPASS_DUNNING_INTERVAL_HOURS", "24")))
    interval_seconds = interval_hours * 3600
    return _bootstrap_scheduled_task(
        component="dunning",
        lock_key="baupass:rq:legacy:dunning:bootstrap",
        lock_ttl_seconds=max(interval_seconds, 3600),
        delay_seconds=30,
        task_fn=run_dunning_cycle_once_task,
        description="legacy.dunning.bootstrap",
    )


def bootstrap_legacy_daily_jobs_scheduler() -> bool:
    interval = max(3600, int(os.getenv("BAUPASS_DAILY_JOBS_SECONDS", "86400")))
    return _bootstrap_scheduled_task(
        component="daily_jobs",
        lock_key="baupass:rq:legacy:daily_jobs:bootstrap",
        lock_ttl_seconds=max(interval, 3600),
        delay_seconds=15,
        task_fn=run_daily_jobs_cycle_once_task,
        description="legacy.daily_jobs.bootstrap",
    )
