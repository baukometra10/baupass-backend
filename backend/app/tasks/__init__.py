"""
WorkPass – Background Task Queue (Redis + RQ)
=============================================
يفصل المهام الثقيلة عن Flask request cycle:
  - إرسال الإيميلات
  - توليد الفواتير
  - فحص انتهاء الوثائق
  - إرسال push notifications
  - مزامنة البيانات
  - تنظيف الجلسات المنتهية

البنية:
  queues:
    critical → مهام فورية لا تتحمل تأخير (auth events, security alerts)
    high     → مهام مهمة (إرسال إيميل فاتورة)
    default  → مهام عادية (تقارير، تنبيهات)
    low      → مهام دورية (تنظيف، إحصاءات)
    scheduled → مهام مجدولة (dunning, document expiry)

الاستخدام:
    from backend.app.tasks import enqueue, enqueue_in
    from backend.app.tasks.email_tasks import send_invoice_email

    # إرسال فوري
    enqueue("high", send_invoice_email, invoice_id="inv-123", company_id=42)

    # إرسال بعد 5 دقائق
    enqueue_in(300, "default", send_invoice_email, invoice_id="inv-123", company_id=42)

تشغيل الـ worker:
    python -m backend.app.tasks.worker
    # أو
    rq worker --url redis://localhost:6379/0 critical high default low scheduled
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable, Optional

logger = logging.getLogger("baupass.tasks")

# ── Queue Priority Order ──────────────────────────────────────────────────────
QUEUE_NAMES = ["critical", "high", "default", "low", "scheduled", "dead_letter"]

# ── Retry Policy بناءً على الـ queue ─────────────────────────────────────────
RETRY_POLICIES = {
    "critical": {"max_retries": 5, "intervals": [10, 30, 60, 120, 300]},
    "high":     {"max_retries": 3, "intervals": [60, 300, 900]},
    "default":  {"max_retries": 3, "intervals": [300, 900, 1800]},
    "low":      {"max_retries": 2, "intervals": [900, 3600]},
    "scheduled":{"max_retries": 1, "intervals": [3600]},
    "dead_letter": {"max_retries": 0, "intervals": []},
}

_rq_queues: dict = {}
_redis_conn = None


def init_task_queues(redis_url: str) -> bool:
    """
    يُهيئ RQ queues.
    يُستدعى من app factory أو worker startup.

    Returns: True إذا نجح، False إذا فشل (Redis غير متاح).
    """
    global _rq_queues, _redis_conn

    if not str(redis_url or "").strip():
        logger.info("Task queues: REDIS_URL not set — background jobs run synchronously.")
        return False

    try:
        import redis
        from rq import Queue

        conn = redis.Redis.from_url(redis_url, decode_responses=False)
        conn.ping()
        _redis_conn = conn

        for name in QUEUE_NAMES:
            policy = RETRY_POLICIES[name]
            _rq_queues[name] = Queue(
                name=name,
                connection=conn,
                default_timeout=600,  # 10 دقائق max لأي task
            )

        logger.info("Task queues initialized: %s", ", ".join(QUEUE_NAMES))
        return True

    except ImportError:
        logger.warning(
            "rq package not installed. Background tasks will run synchronously. "
            "Install: pip install rq"
        )
        return False

    except Exception as exc:
        logger.warning(
            "Failed to connect to Redis for task queue (%s). "
            "Background tasks will run synchronously (degraded mode).",
            exc,
        )
        return False


def enqueue(
    queue_name: str,
    func: Callable,
    *args,
    job_id: Optional[str] = None,
    description: Optional[str] = None,
    **kwargs,
) -> Optional[Any]:
    """
    يُضيف مهمة للـ queue.

    Args:
        queue_name: اسم الـ queue ('critical', 'high', 'default', 'low')
        func: الدالة المطلوب تنفيذها
        *args / **kwargs: arguments للدالة
        job_id: ID مخصص (للـ deduplication)
        description: وصف للمراقبة

    Returns:
        RQ Job object إذا نجح
        None إذا فشل (تُنفَّذ المهمة synchronously كـ fallback)
    """
    if queue_name not in QUEUE_NAMES:
        logger.warning("Unknown queue: %s. Using 'default'.", queue_name)
        queue_name = "default"

    queue = _rq_queues.get(queue_name)

    if queue is None:
        # Fallback: تنفيذ synchronous (في التطوير أو عند غياب Redis)
        logger.warning(
            "Queue '%s' not initialized. Running %s synchronously.",
            queue_name,
            getattr(func, "__name__", str(func)),
        )
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            logger.error("Synchronous task failed: %s", exc)
            return None

    policy = RETRY_POLICIES.get(queue_name, RETRY_POLICIES["default"])

    try:
        from rq import Retry

        job = queue.enqueue(
            func,
            *args,
            **kwargs,
            job_id=job_id,
            description=description or getattr(func, "__name__", "task"),
            retry=Retry(
                max=policy["max_retries"],
                interval=policy["intervals"],
            ),
        )
        logger.debug(
            "Task enqueued: queue=%s func=%s job_id=%s",
            queue_name,
            getattr(func, "__name__", str(func)),
            job.id if job else "-",
        )
        return job

    except Exception as exc:
        logger.error("Failed to enqueue task: %s", exc)
        return None


def enqueue_in(
    delay_seconds: int,
    queue_name: str,
    func: Callable,
    *args,
    job_id: Optional[str] = None,
    description: Optional[str] = None,
    **kwargs,
) -> Optional[Any]:
    """
    يُجدول مهمة للتنفيذ بعد تأخير.

    Args:
        delay_seconds: ثواني الانتظار قبل التنفيذ
        queue_name: اسم الـ queue
        func: الدالة
    """
    queue = _rq_queues.get(queue_name)

    if queue is None:
        logger.warning("Queue not available for delayed task. Task dropped.")
        return None

    try:
        job = queue.enqueue_in(
            timedelta(seconds=delay_seconds),
            func,
            *args,
            job_id=job_id,
            description=description or getattr(func, "__name__", "delayed_task"),
            **kwargs,
        )
        logger.debug(
            "Task scheduled in %ds: queue=%s func=%s",
            delay_seconds,
            queue_name,
            getattr(func, "__name__", str(func)),
        )
        return job

    except Exception as exc:
        logger.error("Failed to schedule task: %s", exc)
        return None


def task_queues_ready() -> bool:
    """True when Redis RQ queues were initialized (background jobs can use rq mode)."""
    return bool(_rq_queues)


def get_queue_stats() -> dict:
    """يُعيد إحصائيات الـ queues للـ monitoring."""
    stats = {}
    for name, queue in _rq_queues.items():
        try:
            stats[name] = {
                "queued": len(queue),
                "failed": queue.failed_job_registry.count,
                "scheduled": queue.scheduled_job_registry.count,
                "started": queue.started_job_registry.count,
            }
        except Exception:
            stats[name] = {"error": "unavailable"}
    return stats


def get_dead_letter_stats(max_preview: int = 5) -> dict:
    """Returns dead-letter metrics captured by worker exception hook."""
    if _redis_conn is None:
        return {"status": "unavailable", "reason": "redis_not_initialized"}

    try:
        key = "baupass:dlq:events"
        total = int(_redis_conn.llen(key) or 0)
        preview_raw = _redis_conn.lrange(key, 0, max(0, max_preview - 1))
        preview = []
        for item in preview_raw:
            try:
                import json
                preview.append(json.loads(item))
            except Exception:
                preview.append({"raw": str(item)})
        return {
            "status": "ok",
            "total_events": total,
            "preview": preview,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def get_worker_heartbeat_stats(max_items: int = 20) -> dict:
    """Returns active worker heartbeat keys from Redis."""
    if _redis_conn is None:
        return {"status": "unavailable", "reason": "redis_not_initialized", "active": 0, "workers": []}

    try:
        pattern = "baupass:worker:heartbeat:*"
        keys = []
        cursor = 0
        while True:
            cursor, batch = _redis_conn.scan(cursor=cursor, match=pattern, count=100)
            if batch:
                keys.extend(batch)
            if cursor == 0:
                break

        workers = []
        for k in sorted(keys)[:max_items]:
            key = k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
            ttl = int(_redis_conn.ttl(k) or 0)
            workers.append({"key": key, "ttl": ttl})

        return {
            "status": "ok",
            "active": len(keys),
            "workers": workers,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc), "active": 0, "workers": []}
