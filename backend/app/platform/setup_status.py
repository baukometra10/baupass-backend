"""Production setup checklist (no secrets)."""
from __future__ import annotations

import os
from typing import Any


def collect_setup_status() -> dict[str, Any]:
    from backend.app.tasks import task_queues_ready

    redis_url = (os.getenv("REDIS_URL") or "").strip()
    return {
        "database": {
            "postgresRuntime": str(os.getenv("BAUPASS_PG_RUNTIME", "0")).strip() in {"1", "true", "yes"},
            "sqlitePath": (os.getenv("BAUPASS_DB_PATH") or "").strip() or "/data/baupass.db",
            "volumeRecommended": "/data",
        },
        "redis": {"configured": bool(redis_url), "queuesReady": task_queues_ready()},
        "workerService": {
            "recommendedCommand": "python -m backend.app.tasks.worker",
            "jobModes": {
                "daily": os.getenv("BAUPASS_DAILY_JOBS_MODE", "inline"),
                "dunning": os.getenv("BAUPASS_DUNNING_MODE", "inline"),
            },
        },
        "mobile": {
            "apkUrl": bool((os.getenv("BAUPASS_WORKER_APK_URL") or "").strip()),
            "testflightUrl": bool((os.getenv("BAUPASS_TESTFLIGHT_URL") or "").strip()),
        },
        "ai": {"openai": bool((os.getenv("OPENAI_API_KEY") or "").strip())},
        "observability": {
            "sentry": bool((os.getenv("SENTRY_DSN") or "").strip()),
            "otel": str(os.getenv("BAUPASS_OTEL", "0")).strip() in {"1", "true", "yes"},
        },
        "billing": {
            "stripe": bool((os.getenv("STRIPE_SECRET_KEY") or "").strip()),
            "stripeWebhook": bool((os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()),
        },
        "smtp": bool((os.getenv("SMTP_HOST") or "").strip() and (os.getenv("SMTP_PASSWORD") or "").strip()),
        "readyScore": _score(redis_url),
        "enterprise": _enterprise_block(),
    }


def _enterprise_block() -> dict[str, Any]:
    try:
        from backend.app.core.enterprise_mode import enterprise_runtime_flags

        return enterprise_runtime_flags()
    except Exception:
        return {"demoAllowed": False, "copilotConfigured": False}


def _score(redis_url: str) -> dict[str, Any]:
    score = 0
    missing: list[str] = []
    checks = [
        (bool((os.getenv("BAUPASS_SECRET_KEY") or "").strip()), "BAUPASS_SECRET_KEY"),
        (bool((os.getenv("BAUPASS_DB_PATH") or "").strip()), "BAUPASS_DB_PATH + Volume /data"),
        (bool(redis_url), "REDIS_URL"),
        (bool((os.getenv("BAUPASS_WORKER_APK_URL") or "").strip()), "BAUPASS_WORKER_APK_URL"),
        (bool((os.getenv("OPENAI_API_KEY") or "").strip()), "OPENAI_API_KEY (Enterprise AI)"),
        (bool((os.getenv("SENTRY_DSN") or "").strip()), "SENTRY_DSN"),
    ]
    for ok, label in checks:
        if ok:
            score += 1
        else:
            missing.append(label)
    return {"percent": int(100 * score / max(1, len(checks))), "missing": missing}
