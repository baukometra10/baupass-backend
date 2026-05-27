"""
Unified platform capability report for operators and global readiness checks.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def collect_platform_capabilities(db_path: Path | None = None) -> dict[str, Any]:
    from backend.app.core.cloud_profile import get_cloud_profile
    from backend.app.db.pg_bootstrap import find_sqlite_data_path, pg_runtime_flag_enabled
    from backend.app.db.runtime import postgres_runtime_enabled
    from backend.app.health.readiness import collect_readiness
    from backend.app.tasks import task_queues_ready
    from backend.server import app

    path = db_path or Path(os.getenv("BAUPASS_DB_PATH", "/data/baupass.db"))
    readiness = collect_readiness(app, path)
    sqlite_path = find_sqlite_data_path()

    attendance = {
        "workerAppNfc": True,
        "workerAppOfflineSync": True,
        "gateScanApi": True,
        "turnstileApi": True,
        "geofenceSiteApp": True,
        "accessLogExport": True,
        "timesheetExport": True,
        "adminV2LiveFeed": True,
        "adminLegacyFullSuite": True,
        "flutterMobileApp": True,
    }

    distribution = {
        "joinPage": True,
        "workerJoinDeepLink": True,
        "ciApkWorkflow": True,
        "ciIosWorkflow": True,
        "apkUrlConfigured": bool((os.getenv("BAUPASS_WORKER_APK_URL") or "").strip()),
        "testflightUrlConfigured": bool((os.getenv("BAUPASS_TESTFLIGHT_URL") or "").strip()),
    }

    data_layer = {
        "runtime": "postgres" if postgres_runtime_enabled() else "sqlite",
        "postgresFlagEnabled": pg_runtime_flag_enabled(),
        "sqlitePath": str(sqlite_path or path),
        "sqliteAutoFallback": pg_runtime_flag_enabled() and not postgres_runtime_enabled(),
        "redisConfigured": bool((os.getenv("REDIS_URL") or "").strip()),
        "taskQueuesReady": task_queues_ready(),
        "coreSchemaReady": readiness.get("checks", {}).get("database", {}).get("ok", False),
    }

    maturity = _score_maturity(readiness, data_layer, distribution)

    return {
        "ok": readiness.get("ready", False),
        "maturityScore": maturity["score"],
        "maturityLevel": maturity["level"],
        "cloud": get_cloud_profile(),
        "readiness": readiness,
        "attendance": attendance,
        "distribution": distribution,
        "dataLayer": data_layer,
        "deferred": {
            "domainsSplitFromServerPy": True,
            "publicAppStoreRelease": not distribution["apkUrlConfigured"],
        },
        "nextSteps": maturity["nextSteps"],
    }


def _score_maturity(readiness: dict, data_layer: dict, distribution: dict) -> dict[str, Any]:
    score = 0
    next_steps: list[str] = []

    if readiness.get("ready"):
        score += 35
    else:
        next_steps.append("Fix database readiness (/api/health/ready).")

    if data_layer.get("runtime") == "sqlite" and data_layer.get("coreSchemaReady"):
        score += 25
    elif data_layer.get("coreSchemaReady"):
        score += 30
    else:
        next_steps.append("Complete DB schema or enable SQLite on /data.")

    if data_layer.get("redisConfigured") and data_layer.get("taskQueuesReady"):
        score += 15
    else:
        next_steps.append("Add Redis + RQ worker service on Railway.")

    if distribution.get("apkUrlConfigured"):
        score += 15
    else:
        next_steps.append("Set BAUPASS_WORKER_APK_URL after CI APK build.")

    if distribution.get("testflightUrlConfigured"):
        score += 10
    else:
        next_steps.append("Optional: configure BAUPASS_TESTFLIGHT_URL for iOS.")

    if score >= 85:
        level = "global_operations_ready"
    elif score >= 65:
        level = "production_ready"
    elif score >= 45:
        level = "pilot_ready"
    else:
        level = "bootstrap"

    return {"score": min(100, score), "level": level, "nextSteps": next_steps}
