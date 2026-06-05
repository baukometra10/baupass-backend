"""Production setup checklist (no secrets)."""
from __future__ import annotations

import os
from typing import Any


def _worker_jwt_secret_weak() -> bool:
    explicit = (os.getenv("BAUPASS_WORKER_JWT_SECRET") or "").strip()
    if explicit and len(explicit) >= 32:
        return False
    fallback = (os.getenv("BAUPASS_DQR_SECRET") or os.getenv("BAUPASS_IDENTITY_TOKEN_SECRET") or "").strip()
    if fallback and len(fallback) >= 32:
        return False
    return True


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
            "jwtSecretStrong": not _worker_jwt_secret_weak(),
            "setupReport": "/api/worker-app/mobile-setup",
        },
        "ai": {"openai": bool((os.getenv("OPENAI_API_KEY") or "").strip())},
        "observability": {
            "sentry": bool((os.getenv("SENTRY_DSN") or "").strip()),
            "otel": str(os.getenv("BAUPASS_OTEL", "0")).strip() in {"1", "true", "yes"},
        },
        "billing": _billing_block(),
        "smtp": bool((os.getenv("SMTP_HOST") or "").strip() and (os.getenv("SMTP_PASSWORD") or "").strip()),
        "cameras": {
            "rtspBridgeToken": bool((os.getenv("BAUPASS_RTSP_BRIDGE_TOKEN") or "").strip()),
            "healthCheck": str(os.getenv("BAUPASS_CAMERA_HEALTH_CHECK", "1")).strip() not in {"0", "false", "off"},
            "nightlyDigest": str(os.getenv("BAUPASS_CAMERA_NIGHTLY_DIGEST", "1")).strip() not in {"0", "false", "off"},
            "docs": "docs/camera-rtsp-bridge-DE.md",
        },
        "readyScore": _score(redis_url),
        "enterprise": _enterprise_block(),
    }


def _billing_block() -> dict[str, Any]:
    from backend.app.platform.pricing import checkout_trial_days, resolve_stripe_price_id

    base = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    plans = ("starter", "professional", "enterprise")
    price_ids = {
        plan: {
            "monthly": bool(resolve_stripe_price_id(plan, annual=False)),
            "annual": bool(resolve_stripe_price_id(plan, annual=True)),
        }
        for plan in plans
    }
    prices_ok = all(v["monthly"] for v in price_ids.values())
    secret_ok = bool((os.getenv("STRIPE_SECRET_KEY") or "").strip())
    webhook_ok = bool((os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip())
    return {
        "stripe": secret_ok,
        "stripeWebhook": webhook_ok,
        "stripePricesConfigured": prices_ok,
        "priceIds": price_ids,
        "checkoutTrialDays": checkout_trial_days(),
        "webhookUrl": f"{base}/api/billing/stripe/webhook" if base else "",
        "bootstrapScript": "python backend/ops/setup_stripe_products.py",
        "readyForCheckout": secret_ok and prices_ok,
        "readyForWebhooks": secret_ok and webhook_ok,
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
        (bool((os.getenv("BAUPASS_TESTFLIGHT_URL") or "").strip()), "BAUPASS_TESTFLIGHT_URL (iPhone)"),
        (not _worker_jwt_secret_weak(), "BAUPASS_WORKER_JWT_SECRET"),
        (bool((os.getenv("OPENAI_API_KEY") or "").strip()), "OPENAI_API_KEY (Enterprise AI)"),
        (bool((os.getenv("SENTRY_DSN") or "").strip()), "SENTRY_DSN"),
    ]
    for ok, label in checks:
        if ok:
            score += 1
        else:
            missing.append(label)
    return {"percent": int(100 * score / max(1, len(checks))), "missing": missing}
