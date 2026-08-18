"""
WorkPass – RQ Worker Startup
=============================
تشغيل:
    python -m backend.app.tasks.worker
    python -m backend.app.tasks.worker --queues critical high
    python -m backend.app.tasks.worker --burst  (ينتهي عند إفراغ الـ queues)

في الإنتاج (systemd):
    [Unit]
    Description=SUPPIX RQ Worker
    After=network.target redis.service

    [Service]
    User=baupass
    WorkingDirectory=/opt/baupass
    ExecStart=/opt/baupass/.venv/bin/python -m backend.app.tasks.worker
    Restart=always
    RestartSec=5
    Environment="BAUPASS_ENV=production"

    [Install]
    WantedBy=multi-user.target
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import socket
import threading
import time

logger = logging.getLogger("baupass.worker")


def _start_worker_heartbeat(redis_conn) -> threading.Event:
    stop_event = threading.Event()
    host = socket.gethostname() or "unknown"
    pid = os.getpid()
    key = f"baupass:worker:heartbeat:{host}:{pid}"
    interval = max(5, int(os.getenv("BAUPASS_RQ_HEARTBEAT_SECONDS", "10")))
    ttl = max(interval * 3, 30)

    def _loop():
        while not stop_event.is_set():
            try:
                redis_conn.set(key, str(int(time.time())), ex=ttl)
            except Exception:
                pass
            stop_event.wait(interval)

    th = threading.Thread(target=_loop, name="baupass-rq-worker-heartbeat", daemon=True)
    th.start()
    return stop_event


def _dead_letter_exception_handler(job, exc_type, exc_value, tb):
    try:
        from .dead_letter import push_dead_letter_event
        push_dead_letter_event(
            job.connection,
            job_id=str(getattr(job, "id", "-")),
            func_name=str(getattr(job, "func_name", "-")),
            queue_name=str(getattr(getattr(job, "origin", None), "name", "") or getattr(job, "origin", "-")),
            error=f"{exc_type.__name__}: {exc_value}",
        )
    except Exception:
        pass
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="SUPPIX RQ Background Worker")
    parser.add_argument(
        "--queues",
        nargs="+",
        default=["critical", "high", "default", "low", "scheduled"],
        help="Queue names to process (in priority order)",
    )
    parser.add_argument("--burst", action="store_true", help="Exit after processing all jobs")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    try:
        import redis
        from rq import Worker, Queue

        conn = redis.Redis.from_url(redis_url, decode_responses=False)
        conn.ping()
        logger.info("Worker connected to Redis: %s", redis_url.split("@")[-1])

        heartbeat_stop = _start_worker_heartbeat(conn)

        queues = [Queue(name, connection=conn) for name in args.queues]
        logger.info("Processing queues: %s", ", ".join(args.queues))

        worker = Worker(queues, connection=conn, exception_handlers=[_dead_letter_exception_handler])
        try:
            worker.work(burst=args.burst, with_scheduler=True)
        finally:
            heartbeat_stop.set()

    except ImportError:
        logger.error("rq package not installed. Run: pip install rq")
        return 1
    except Exception as exc:
        logger.error("Worker failed to start: %s", exc)
        return 1

    return 0


_embedded_started = False


def rq_modes_enabled() -> bool:
    return any(
        str(os.getenv(name, "thread")).strip().lower() == "rq"
        for name in (
            "BAUPASS_INVOICE_RETRY_MODE",
            "BAUPASS_WORKER_SESSION_CLEANUP_MODE",
            "BAUPASS_DAILY_JOBS_MODE",
            "BAUPASS_DUNNING_MODE",
        )
    )


def start_embedded_worker(queue_names: list[str] | None = None) -> bool:
    """Run the RQ worker in a daemon thread inside the web process.

    Railway volumes are 1:1 with a service, so a second worker container cannot
    share SQLite at /data. Embedding the worker keeps heartbeats and jobs on
    the same database. Disable with BAUPASS_EMBED_RQ_WORKER=0 when a dedicated
    worker service is attached to Postgres.
    """
    global _embedded_started
    if _embedded_started:
        return True
    if str(os.getenv("BAUPASS_ENV", "")).strip().lower() == "testing":
        return False
    if str(os.getenv("BAUPASS_EMBED_RQ_WORKER", "1")).strip().lower() in {"0", "false", "no", "off"}:
        return False
    if not rq_modes_enabled():
        return False
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    if not redis_url:
        logger.warning("Embedded RQ worker skipped: REDIS_URL is empty")
        return False

    names = queue_names or ["critical", "high", "default", "low", "scheduled"]

    def _run() -> None:
        try:
            import redis
            from rq import Queue, Worker

            conn = redis.Redis.from_url(redis_url, decode_responses=False)
            conn.ping()
            heartbeat_stop = _start_worker_heartbeat(conn)
            queues = [Queue(name, connection=conn) for name in names]
            worker = Worker(queues, connection=conn, exception_handlers=[_dead_letter_exception_handler])
            try:
                worker.work(burst=False, with_scheduler=True)
            finally:
                heartbeat_stop.set()
        except Exception:
            logger.exception("Embedded RQ worker stopped")

    threading.Thread(target=_run, name="baupass-embedded-rq", daemon=True).start()
    _embedded_started = True
    logger.info("Embedded RQ worker started for queues: %s", ", ".join(names))
    return True


if __name__ == "__main__":
    sys.exit(main())
