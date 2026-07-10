"""Public readiness report for SUPPIX hybrid worker mobile (no secret values)."""
from __future__ import annotations

import os
from typing import Any


def _configured(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def _weak_worker_jwt_secret() -> bool:
    explicit = (os.getenv("BAUPASS_WORKER_JWT_SECRET") or "").strip()
    if explicit and len(explicit) >= 32:
        return False
    fallback = (os.getenv("BAUPASS_DQR_SECRET") or os.getenv("BAUPASS_IDENTITY_TOKEN_SECRET") or "").strip()
    if fallback and len(fallback) >= 32:
        return False
    return True


def collect_worker_mobile_setup() -> dict[str, Any]:
    from backend.app.platform.push.delivery import push_platform_status
    from backend.app.platform.security.worker_devices import (
        worker_device_binding_enabled,
        worker_jwt_enabled,
    )

    public_base = (os.getenv("PUBLIC_BASE_URL") or os.getenv("BAUPASS_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    pg_runtime = str(os.getenv("BAUPASS_PG_RUNTIME", "0")).strip().lower() in {"1", "true", "yes"}
    db_ok = _configured("DATABASE_URL") if pg_runtime else _configured("BAUPASS_DB_PATH")

    fcm_v1 = _configured("FCM_PROJECT_ID") and (
        _configured("FCM_SERVICE_ACCOUNT_JSON") or _configured("FCM_SERVICE_ACCOUNT_B64")
    )
    fcm_legacy = _configured("FCM_SERVER_KEY") or _configured("FIREBASE_SERVER_KEY")

    env_keys: list[dict[str, Any]] = [
        {
            "id": "PUBLIC_BASE_URL",
            "group": "core",
            "required": True,
            "configured": _configured("PUBLIC_BASE_URL"),
            "hint": "HTTPS Railway URL — join.html, QR, deep links",
        },
        {
            "id": "BAUPASS_SECRET_KEY",
            "group": "core",
            "required": True,
            "configured": _configured("BAUPASS_SECRET_KEY"),
            "hint": "64+ random chars",
        },
        {
            "id": "BAUPASS_AUDIT_SIGNING_KEY",
            "group": "core",
            "required": True,
            "configured": _configured("BAUPASS_AUDIT_SIGNING_KEY"),
            "hint": "Audit log signing",
        },
        {
            "id": "BAUPASS_DB_PATH",
            "group": "database",
            "required": not pg_runtime,
            "configured": _configured("BAUPASS_DB_PATH"),
            "hint": "SQLite on Volume /data — set BAUPASS_PG_RUNTIME=0",
        },
        {
            "id": "DATABASE_URL",
            "group": "database",
            "required": pg_runtime,
            "configured": _configured("DATABASE_URL"),
            "hint": "PostgreSQL when BAUPASS_PG_RUNTIME=1",
        },
        {
            "id": "BAUPASS_WORKER_JWT_SECRET",
            "group": "worker_app",
            "required": True,
            "configured": not _weak_worker_jwt_secret(),
            "hint": "Dedicated JWT secret for worker sessions (32+ chars)",
        },
        {
            "id": "BAUPASS_TESTFLIGHT_URL",
            "group": "distribution",
            "required": True,
            "platform": "iphone",
            "configured": _configured("BAUPASS_TESTFLIGHT_URL"),
            "hint": "https://testflight.apple.com/join/… — iPhone internal install",
        },
        {
            "id": "BAUPASS_WORKER_APK_URL",
            "group": "distribution",
            "required": False,
            "platform": "android",
            "configured": _configured("BAUPASS_WORKER_APK_URL"),
            "hint": "Hosted APK for join.html (Android sideload)",
        },
        {
            "id": "REDIS_URL",
            "group": "jobs",
            "required": False,
            "configured": _configured("REDIS_URL"),
            "hint": "Recommended + worker service for session cleanup",
        },
        {
            "id": "FCM_PROJECT_ID + FCM_SERVICE_ACCOUNT_JSON",
            "group": "push",
            "required": False,
            "configured": fcm_v1 or fcm_legacy,
            "hint": "Push notifications to Flutter app (optional for login/NFC)",
        },
    ]

    missing_required = [k["id"] for k in env_keys if k.get("required") and not k["configured"]]
    core_ok = db_ok and _configured("PUBLIC_BASE_URL") and _configured("BAUPASS_SECRET_KEY")
    jwt_ok = not _weak_worker_jwt_secret()
    iphone_ok = core_ok and jwt_ok and _configured("BAUPASS_TESTFLIGHT_URL")
    android_ok = core_ok and jwt_ok and _configured("BAUPASS_WORKER_APK_URL")

    push_status = push_platform_status()
    return {
        "workerAppKind": "hybrid_flutter",
        "publicBaseUrl": public_base or None,
        "joinPage": f"{public_base}/join.html" if public_base else None,
        "joinConfigPath": "/worker-join-config.json",
        "deepLinkScheme": "baupass://join",
        "flutterBuildDefine": "BAUPASS_API_URL=<same as PUBLIC_BASE_URL>",
        "security": {
            "deviceBindingEnabled": worker_device_binding_enabled(),
            "jwtEnabled": worker_jwt_enabled(),
            "jwtSecretStrong": not _weak_worker_jwt_secret(),
        },
        "database": {
            "postgresRuntime": pg_runtime,
            "persistentSqlitePath": (os.getenv("BAUPASS_DB_PATH") or "/data/baupass.db").strip(),
            "configured": db_ok,
        },
        "distribution": {
            "testFlightUrlConfigured": _configured("BAUPASS_TESTFLIGHT_URL"),
            "apkUrlConfigured": _configured("BAUPASS_WORKER_APK_URL"),
            "playStoreConfigured": _configured("BAUPASS_PLAY_STORE_URL"),
            "appStoreConfigured": _configured("BAUPASS_APP_STORE_URL"),
        },
        "push": {
            "configured": bool(push_status.get("ok")),
            "channel": push_status.get("channel"),
            "hint": push_status.get("hint"),
        },
        "envKeys": env_keys,
        "missingRequired": missing_required,
        "readiness": {
            "coreBackend": core_ok and db_ok,
            "iphoneTestFlight": iphone_ok,
            "androidApkLink": core_ok and _configured("BAUPASS_WORKER_APK_URL"),
            "pushNotifications": bool(push_status.get("ok")),
        },
        "docs": {
            "arabic": "/docs/iphone-testflight-railway-AR.md",
            "envTemplate": "/.env.worker-mobile.example",
            "launchSequence": "/docs/LAUNCH-SEQUENCE-DE.md",
            "e2eChecklist": "/docs/qr-worker-e2e-checklist-DE.md",
            "storeListing": "/docs/store-listing-DE.md",
        },
    }
