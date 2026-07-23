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


def _email_status_block() -> dict[str, Any]:
    smtp_host = (os.getenv("SMTP_HOST") or "").strip()
    smtp_pass = (os.getenv("SMTP_PASSWORD") or "").strip()
    resend = (os.getenv("RESEND_API_KEY") or os.getenv("RESEND_KEY") or "").strip()
    brevo = (os.getenv("BREVO_API_KEY") or "").strip()
    outbound = bool((smtp_host and smtp_pass) or resend or brevo)
    imap_host = (
        os.getenv("BAUPASS_IMAP_HOST")
        or os.getenv("SUPPIX_IMAP_HOST")
        or os.getenv("IMAP_HOST")
        or ""
    ).strip()
    imap_user = (
        os.getenv("BAUPASS_IMAP_USERNAME")
        or os.getenv("SUPPIX_IMAP_USERNAME")
        or os.getenv("IMAP_USERNAME")
        or ""
    ).strip()
    imap_pass = (
        os.getenv("BAUPASS_IMAP_PASSWORD")
        or os.getenv("SUPPIX_IMAP_PASSWORD")
        or os.getenv("IMAP_PASSWORD")
        or ""
    ).strip()
    imap_configured = bool(imap_host and imap_user and imap_pass)
    return {
        "outboundConfigured": outbound,
        "imapConfigured": imap_configured,
        "configured": outbound or imap_configured,
        "smtp": outbound,
    }


def _database_block() -> dict[str, Any]:
    pg_runtime = str(os.getenv("BAUPASS_PG_RUNTIME", "0")).strip().lower() in {"1", "true", "yes"}
    sqlite_path = (os.getenv("BAUPASS_DB_PATH") or "").strip() or "/data/baupass.db"
    exists = False
    size_bytes = 0
    persistent = False
    login_ready = True
    hints: list[str] = []
    try:
        from pathlib import Path

        from backend.server import DB_PATH, get_database_runtime_info

        info = get_database_runtime_info()
        persistent = bool(info.get("persistent"))
        db_file = Path(DB_PATH)
        exists = db_file.is_file()
        size_bytes = int(db_file.stat().st_size) if exists else 0
        if not pg_runtime:
            if not exists or size_bytes < 4096:
                login_ready = False
                hints.append(
                    "SQLite-Datei fehlt oder ist leer — Volume auf /data mounten und "
                    "BAUPASS_DB_PATH=/data/baupass.db setzen, dann Redeploy."
                )
            if (os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_GIT_COMMIT_SHA")) and not persistent:
                hints.append(
                    "DB liegt nicht auf /data — bei jedem Deploy gehen Benutzer/Login-Daten verloren."
                )
        else:
            from backend.app.db.pg_bootstrap import missing_core_tables

            missing = missing_core_tables()
            if missing:
                login_ready = False
                hints.append(
                    "PostgreSQL-Schema unvollständig — BAUPASS_PG_RUNTIME=0 mit SQLite-Volume "
                    f"oder Migration ausführen. Fehlend: {', '.join(missing[:6])}."
                )
    except Exception as exc:
        login_ready = False
        hints.append(str(exc)[:240])

    return {
        "postgresRuntime": pg_runtime,
        "sqlitePath": sqlite_path,
        "volumeRecommended": "/data",
        "sqliteFileExists": exists,
        "sqliteSizeBytes": size_bytes,
        "persistent": persistent,
        "loginReady": login_ready,
        "railwayHints": hints,
    }


def collect_setup_status() -> dict[str, Any]:
    from backend.app.tasks import task_queues_ready
    from backend.app.tasks.job_health import collect_background_jobs_health, get_rq_mode_summary

    redis_url = (os.getenv("REDIS_URL") or "").strip()
    background_jobs = collect_background_jobs_health()
    rq_modes = get_rq_mode_summary()
    any_rq = any(mode == "rq" for mode in rq_modes.values())
    workers = background_jobs.get("workers") or {}
    worker_active = int(workers.get("active") or 0)
    worker_checklist: list[dict[str, Any]] = [
        {
            "id": "redis",
            "label": "REDIS_URL",
            "ok": bool(redis_url),
            "hint": "Redis für RQ-Queues und Job-Status.",
        },
        {
            "id": "rq_worker",
            "label": "RQ Worker-Prozess",
            "ok": (not any_rq) or worker_active >= 1,
            "hint": "Separater Railway-Service: python -m backend.app.tasks.worker",
            "activeWorkers": worker_active,
        },
    ]
    for name, mode in rq_modes.items():
        if mode == "rq":
            job_ok = str((background_jobs.get("jobs") or {}).get(name, {}).get("status") or "") != "error"
            worker_checklist.append(
                {
                    "id": f"job_{name}",
                    "label": f"Job {name} (RQ)",
                    "ok": job_ok and worker_active >= 1,
                    "mode": mode,
                }
            )
    return {
        "database": _database_block(),
        "redis": {"configured": bool(redis_url), "queuesReady": task_queues_ready()},
        "backgroundJobs": background_jobs,
        "workerService": {
            "recommendedCommand": "python -m backend.app.tasks.worker",
            "railwayServiceType": "worker",
            "startCommand": "python -m backend.app.tasks.worker",
            "healthEndpoint": "/api/health",
            "jobModes": rq_modes,
            "anyRqMode": any_rq,
            "activeWorkers": worker_active,
            "checklist": worker_checklist,
            "ready": all(item.get("ok") for item in worker_checklist),
        },
        "mobile": {
            "apkUrl": bool((os.getenv("BAUPASS_WORKER_APK_URL") or "").strip()),
            "testflightUrl": bool((os.getenv("BAUPASS_TESTFLIGHT_URL") or "").strip()),
            "playStoreUrl": bool((os.getenv("BAUPASS_PLAY_STORE_URL") or "").strip()),
            "appStoreUrl": bool((os.getenv("BAUPASS_APP_STORE_URL") or "").strip()),
            "distributionApi": "/api/v2/mobile/distribution",
            "jwtSecretStrong": not _worker_jwt_secret_weak(),
            "setupReport": "/api/worker-app/mobile-setup",
        },
        "ai": {"openai": bool((os.getenv("OPENAI_API_KEY") or "").strip())},
        "observability": {
            "sentry": bool((os.getenv("SENTRY_DSN") or "").strip()),
            "otel": str(os.getenv("BAUPASS_OTEL", "0")).strip() in {"1", "true", "yes"},
        },
        "billing": _billing_block(),
        "sms": _sms_block(),
        "email": _email_status_block(),
        "smtp": _email_status_block()["outboundConfigured"],
        "channels": _channels_alerts(),
        "cameras": {
            "rtspBridgeToken": bool((os.getenv("BAUPASS_RTSP_BRIDGE_TOKEN") or "").strip()),
            "healthCheck": str(os.getenv("BAUPASS_CAMERA_HEALTH_CHECK", "1")).strip() not in {"0", "false", "off"},
            "nightlyDigest": str(os.getenv("BAUPASS_CAMERA_NIGHTLY_DIGEST", "1")).strip() not in {"0", "false", "off"},
            "docs": "docs/camera-rtsp-bridge-DE.md",
        },
        "readyScore": _score(redis_url),
        "enterprise": _enterprise_block(),
        "launchDocs": {
            "sequence": "/docs/LAUNCH-SEQUENCE-DE.md",
            "e2e": "/docs/qr-worker-e2e-checklist-DE.md",
            "store": "/docs/store-listing-DE.md",
            "workerService": "/deploy/railway-worker.service.md",
            "verifyScript": "deploy/railway-launch-verify.ps1",
        },
    }


def _sms_block() -> dict[str, Any]:
    try:
        from backend.app.platform.notifications.sms import sms_configured

        configured = bool(sms_configured())
    except Exception:
        configured = False
    return {
        "configured": configured,
        "provider": "twilio" if configured else "",
        "hint": "TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN + TWILIO_FROM_NUMBER",
    }


def _channels_alerts() -> list[dict[str, Any]]:
    """Critical channel readiness for Platform / ops dashboards."""
    billing = _billing_block()
    email = _email_status_block()
    sms = _sms_block()
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    openai = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    alerts = [
        {
            "id": "sms",
            "label": "SMS (Twilio)",
            "ok": sms.get("configured"),
            "severity": "warn" if not sms.get("configured") else "ok",
            "hint": sms.get("hint") or "",
        },
        {
            "id": "email",
            "label": "E-Mail outbound",
            "ok": email.get("outboundConfigured"),
            "severity": "warn" if not email.get("outboundConfigured") else "ok",
            "hint": "SMTP_HOST/SMTP_PASSWORD oder RESEND_API_KEY / BREVO_API_KEY",
        },
        {
            "id": "stripe",
            "label": "Stripe billing",
            "ok": billing.get("readyForCheckout"),
            "severity": "warn" if not billing.get("readyForCheckout") else "ok",
            "hint": "STRIPE_SECRET_KEY + Price IDs",
        },
        {
            "id": "redis",
            "label": "Redis / queues",
            "ok": bool(redis_url),
            "severity": "warn" if not redis_url else "ok",
            "hint": "REDIS_URL",
        },
        {
            "id": "openai",
            "label": "OpenAI API",
            "ok": openai,
            "severity": "warn" if not openai else "ok",
            "hint": "OPENAI_API_KEY (ChatGPT Plus ≠ API)",
        },
    ]
    return alerts


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
        "webhookUrl": f"{base}/api/v2/billing/stripe/webhook" if base else "",
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
    try:
        db_block = _database_block()
        if not db_block.get("loginReady"):
            missing.append("SQLite login-ready (Volume /data + BAUPASS_DB_PATH)")
    except Exception:
        pass
    return {"percent": int(100 * score / max(1, len(checks))), "missing": missing}


def alert_critical_channels_if_needed(db) -> dict[str, Any]:
    """Create deduped system alerts for missing production channels."""
    from backend.server import create_system_alert

    alerts = _channels_alerts()
    created: list[str] = []
    for ch in alerts:
        if ch.get("ok"):
            continue
        # Soft-skip OpenAI in non-enterprise setups unless explicitly required.
        if ch.get("id") == "openai" and str(os.getenv("BAUPASS_REQUIRE_OPENAI", "0")).strip() not in {
            "1",
            "true",
            "yes",
        }:
            continue
        aid = create_system_alert(
            db,
            code=f"channel_down_{ch.get('id')}",
            severity="warning",
            message=f"Kanal nicht bereit: {ch.get('label')}",
            details={"channel": ch.get("id"), "hint": ch.get("hint") or ""},
            dedup_minutes=60 * 12,
        )
        if aid:
            created.append(str(ch.get("id")))
    return {"checked": len(alerts), "alerted": created, "channels": alerts}
