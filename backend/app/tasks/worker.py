"""
BauPass – RQ Worker Startup
=============================
تشغيل:
    python -m backend.app.tasks.worker
    python -m backend.app.tasks.worker --queues critical high
    python -m backend.app.tasks.worker --burst  (ينتهي عند إفراغ الـ queues)

في الإنتاج (systemd):
    [Unit]
    Description=BauPass RQ Worker
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
    parser = argparse.ArgumentParser(description="BauPass RQ Background Worker")
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
        from rq import Worker, Queue, Connection

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


if __name__ == "__main__":
    sys.exit(main())
