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
        "sqliteReplicaUnsafe": not postgres_runtime_enabled(),
        "recommendedWebReplicas": 2 if postgres_runtime_enabled() and bool((os.getenv("REDIS_URL") or "").strip()) else 1,
    }

    maturity = _score_maturity(readiness, data_layer, distribution)

    from backend.app.platform.enterprise.datev_client import datev_env_configured
    from backend.app.platform.ha.posture import collect_ha_posture

    ha = collect_ha_posture()

    personio_live = (os.getenv("BAUPASS_PERSONIO_ENABLED") or "0").strip().lower() in {"1", "true", "yes"}
    zapier_live = (os.getenv("BAUPASS_ZAPIER_ENABLED") or "0").strip().lower() in {"1", "true", "yes"}

    do_not_promise = [
        "DATEV LODAS certified",
        "DATEV Unternehmen online certified",
        "ELSTER certified transmission",
    ]
    if not personio_live:
        do_not_promise.append("Personio")
    if not zapier_live:
        do_not_promise.append("Zapier/Make")

    live = ["public_api", "webhooks", "workpass_lohn", "datev_csv", "stripe", "oidc", "saml", "rtsp", "gps", "sap_oracle_export"]
    if personio_live:
        live.append("personio")
    if zapier_live:
        live.append("zapier_make")

    integrations = {
        "datevCsvExport": True,
        "datevOauthClient": bool(datev_env_configured()),
        "datevLodasCertified": False,
        "datevLodasPartnerReady": True,
        "datevUnternehmenOnline": False,
        "elster": False,
        "elsterPartnerReady": True,
        "personio": bool(personio_live),
        "zapier": bool(zapier_live),
        "samlProduction": True,
        "live": live,
        "doNotPromiseInContracts": do_not_promise,
    }

    multi_region = {
        "automaticFailover": False,
        "codeReady": bool(ha.get("score", 0) >= 70),
        "guide": "docs/multi-region-deployment-AR.md",
        "requires": ["postgres", "redis", "object_storage", "dual_replica_stable"],
        "status": "ready_after_ha" if ha.get("score", 0) >= 70 else "blocked_until_ha",
    }

    return {
        "ok": readiness.get("ready", False),
        "maturityScore": maturity["score"],
        "maturityLevel": maturity["level"],
        "cloud": get_cloud_profile(),
        "readiness": readiness,
        "attendance": attendance,
        "distribution": distribution,
        "dataLayer": data_layer,
        "ha": ha,
        "multiRegion": multi_region,
        "integrations": integrations,
        "deferred": {
            "domainsSplitFromServerPy": True,
            "publicAppStoreRelease": not distribution["apkUrlConfigured"],
            "datevLodasOfficialCertification": True,
            "elsterAuthorityEnrollment": True,
        },
        "nextSteps": list(dict.fromkeys([*(maturity["nextSteps"] or []), *(ha.get("nextSteps") or [])])),
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
