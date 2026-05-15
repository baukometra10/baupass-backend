from __future__ import annotations

import importlib
import logging
import os
import time
from typing import Any

from . import enqueue_in

logger = logging.getLogger("baupass.tasks.legacy")


def _import_legacy_server():
    # Prevent legacy module import from spawning its own background threads.
    os.environ.setdefault("BAUPASS_ENABLE_BACKGROUND_JOBS", "0")
    os.environ.setdefault("BAUPASS_ENABLE_IMAP_POLLER", "0")
    return importlib.import_module("backend.server")


def run_invoice_retry_cycle_once_task(*, reschedule: bool = True) -> dict[str, Any]:
    """Runs legacy invoice retry cycle once, then schedules the next run."""
    legacy = _import_legacy_server()
    result = legacy.run_invoice_retry_cycle_once()

    if reschedule:
        interval = max(60, int(os.getenv("BAUPASS_INVOICE_RETRY_SECONDS", "180")))
        enqueue_in(
            interval,
            "scheduled",
            run_invoice_retry_cycle_once_task,
            reschedule=True,
            description="legacy.invoice_retry.cycle",
        )

    return result


def bootstrap_legacy_invoice_retry_scheduler() -> bool:
    """Enqueues the first scheduled retry cycle once per deployment window."""
    interval = max(60, int(os.getenv("BAUPASS_INVOICE_RETRY_SECONDS", "180")))
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    lock_key = "baupass:rq:legacy:invoice_retry:bootstrap"

    try:
        import redis

        conn = redis.Redis.from_url(redis_url, decode_responses=True)
        lock_acquired = bool(conn.set(lock_key, str(int(time.time())), nx=True, ex=max(300, interval * 2)))
        if not lock_acquired:
            logger.info("Legacy invoice retry scheduler already bootstrapped")
            return False

        enqueue_in(
            5,
            "scheduled",
            run_invoice_retry_cycle_once_task,
            reschedule=True,
            description="legacy.invoice_retry.bootstrap",
        )
        logger.info("Legacy invoice retry scheduler bootstrapped via RQ")
        return True
    except Exception as exc:
        logger.error("Failed to bootstrap legacy invoice retry scheduler: %s", exc)
        return False


def run_worker_session_cleanup_cycle_once_task(*, reschedule: bool = True) -> dict[str, Any]:
    """Runs legacy worker-session cleanup once, then schedules the next run."""
    legacy = _import_legacy_server()
    result = legacy.run_worker_session_cleanup_cycle_once()

    if reschedule:
        interval = max(60, int(os.getenv("BAUPASS_WORKER_SESSION_CLEANUP_SECONDS", "300")))
        enqueue_in(
            interval,
            "scheduled",
            run_worker_session_cleanup_cycle_once_task,
            reschedule=True,
            description="legacy.worker_session_cleanup.cycle",
        )

    return result


def bootstrap_legacy_worker_session_cleanup_scheduler() -> bool:
    """Enqueues the first worker-session cleanup cycle once per deployment window."""
    interval = max(60, int(os.getenv("BAUPASS_WORKER_SESSION_CLEANUP_SECONDS", "300")))
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    lock_key = "baupass:rq:legacy:worker_session_cleanup:bootstrap"

    try:
        import redis

        conn = redis.Redis.from_url(redis_url, decode_responses=True)
        lock_acquired = bool(conn.set(lock_key, str(int(time.time())), nx=True, ex=max(300, interval * 2)))
        if not lock_acquired:
            logger.info("Legacy worker session cleanup scheduler already bootstrapped")
            return False

        enqueue_in(
            5,
            "scheduled",
            run_worker_session_cleanup_cycle_once_task,
            reschedule=True,
            description="legacy.worker_session_cleanup.bootstrap",
        )
        logger.info("Legacy worker session cleanup scheduler bootstrapped via RQ")
        return True
    except Exception as exc:
        logger.error("Failed to bootstrap legacy worker session cleanup scheduler: %s", exc)
        return False


def run_daily_jobs_cycle_once_task(*, reschedule: bool = True) -> dict[str, Any]:
    """Runs legacy daily jobs cycle once, then schedules the next run."""
    legacy = _import_legacy_server()
    result = legacy.run_daily_jobs_cycle_once()

    if reschedule:
        interval = max(3600, int(os.getenv("BAUPASS_DAILY_JOBS_SECONDS", "86400")))
        enqueue_in(
            interval,
            "scheduled",
            run_daily_jobs_cycle_once_task,
            reschedule=True,
            description="legacy.daily_jobs.cycle",
        )

    return result


def run_dunning_cycle_once_task(*, reschedule: bool = True) -> dict[str, Any]:
    """Runs legacy dunning + backup rotation once, then schedules the next run."""
    legacy = _import_legacy_server()
    with legacy.app.app_context():
        legacy.run_dunning_job_once()
    result = {"ok": True}

    if reschedule:
        interval_hours = max(1, int(os.getenv("BAUPASS_DUNNING_INTERVAL_HOURS", "24")))
        interval_seconds = interval_hours * 3600
        enqueue_in(
            interval_seconds,
            "scheduled",
            run_dunning_cycle_once_task,
            reschedule=True,
            description="legacy.dunning.cycle",
        )

    return result


def bootstrap_legacy_dunning_scheduler() -> bool:
    """Enqueues the first dunning cycle once per deployment window."""
    interval_hours = max(1, int(os.getenv("BAUPASS_DUNNING_INTERVAL_HOURS", "24")))
    interval_seconds = interval_hours * 3600
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    lock_key = "baupass:rq:legacy:dunning:bootstrap"

    try:
        import redis

        conn = redis.Redis.from_url(redis_url, decode_responses=True)
        lock_acquired = bool(conn.set(lock_key, str(int(time.time())), nx=True, ex=max(600, int(interval_seconds * 0.1))))
        if not lock_acquired:
            logger.info("Legacy dunning scheduler already bootstrapped")
            return False

        enqueue_in(
            30,
            "scheduled",
            run_dunning_cycle_once_task,
            reschedule=True,
            description="legacy.dunning.bootstrap",
        )
        logger.info("Legacy dunning scheduler bootstrapped via RQ")
        return True
    except Exception as exc:
        logger.error("Failed to bootstrap legacy dunning scheduler: %s", exc)
        return False


def bootstrap_legacy_daily_jobs_scheduler() -> bool:
    """Enqueues the first daily jobs cycle once per deployment window."""
    interval = max(3600, int(os.getenv("BAUPASS_DAILY_JOBS_SECONDS", "86400")))
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    lock_key = "baupass:rq:legacy:daily_jobs:bootstrap"

    try:
        import redis

        conn = redis.Redis.from_url(redis_url, decode_responses=True)
        lock_acquired = bool(conn.set(lock_key, str(int(time.time())), nx=True, ex=max(600, int(interval * 0.1))))
        if not lock_acquired:
            logger.info("Legacy daily jobs scheduler already bootstrapped")
            return False

        enqueue_in(
            15,
            "scheduled",
            run_daily_jobs_cycle_once_task,
            reschedule=True,
            description="legacy.daily_jobs.bootstrap",
        )
        logger.info("Legacy daily jobs scheduler bootstrapped via RQ")
        return True
    except Exception as exc:
        logger.error("Failed to bootstrap legacy daily jobs scheduler: %s", exc)
        return False
