"""
Hyper-Scale Infrastructure Layer — deployment readiness snapshot.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def build_infrastructure_layer(db_path: Path) -> dict[str, Any]:
    from backend.app.core.cloud_profile import get_cloud_profile
    from backend.app.database import get_database_health
    from backend.app.db.runtime import postgres_runtime_enabled
    from backend.app.health.dr_status import collect_dr_status

    cloud = get_cloud_profile()
    postgres = postgres_runtime_enabled()
    redis_url = bool(os.getenv("REDIS_URL", "").strip())
    replica_raw = os.getenv("BAUPASS_WEB_REPLICAS") or os.getenv("SUPPIX_WEB_REPLICAS") or "1"
    try:
        replica_n = int(replica_raw)
    except ValueError:
        replica_n = 1

    from backend.app.platform.ha.posture import collect_ha_posture, object_storage_status

    ha = collect_ha_posture()
    storage = object_storage_status()

    return {
        "layer": "hyper_scale_infrastructure",
        "status": "ha_production" if ha.get("score", 0) >= 95 else ("active" if postgres else "single_node"),
        "kubernetes": {
            "configured": False,
            "manifests": None,
            "hpa": None,
            "health_probes": True,
            "note": "not_configured — this repository has no deploy/k8s manifests or HPA.",
        },
        "multi_region": {
            "strategy": cloud.get("regionStrategy"),
            "active_regions": cloud.get("activeRegions"),
            "current_region": cloud.get("region"),
            "guide": "docs/multi-region-deployment-AR.md",
            "automaticFailover": False,
            "codeReady": True,
            "status": "ready_after_ha" if ha.get("score", 0) >= 70 else "blocked_until_ha",
        },
        "cdn": {
            "edge_headers": True,
            "cache_seconds": int(os.getenv("BAUPASS_CDN_CACHE_SECONDS", "86400")),
        },
        "object_storage": storage,
        "high_availability": {
            "postgres": postgres,
            "redis_configured": redis_url,
            "rq_worker": "python -m backend.app.tasks.worker",
            "sqliteReplicaUnsafe": not postgres,
            "recommendedWebReplicas": 2 if postgres and redis_url else 1,
            "configuredWebReplicas": replica_n,
            "posture": ha,
            "note": "Never run more than one web replica against SQLite on /data.",
            "cutoverGuide": "docs/ops/railway-ha-cutover.md",
            "postgresBackup": {
                "script": "backend/ops/postgres_dr_snapshot.py --dump",
                "bootFlag": "BAUPASS_PG_DR_SNAPSHOT_ON_BOOT",
                "scheduleFlag": "BAUPASS_PG_DR_SNAPSHOT_SCHEDULE",
                "ready": postgres,
            },
        },
        "database": get_database_health(),
        "dr": collect_dr_status(db_path),
    }
