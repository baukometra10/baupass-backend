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
    return {
        "layer": "hyper_scale_infrastructure",
        "status": "active",
        "kubernetes": {
            "manifests": "deploy/k8s/",
            "hpa": "deploy/k8s/hpa.yaml",
            "health_probes": True,
        },
        "multi_region": {
            "strategy": cloud.get("regionStrategy"),
            "active_regions": cloud.get("activeRegions"),
            "current_region": cloud.get("region"),
            "guide": "docs/multi-region-deployment-AR.md",
        },
        "cdn": {
            "edge_headers": True,
            "cache_seconds": int(os.getenv("BAUPASS_CDN_CACHE_SECONDS", "86400")),
        },
        "object_storage": os.getenv("BAUPASS_OBJECT_STORAGE", "local"),
        "high_availability": {
            "postgres": postgres_runtime_enabled(),
            "redis_configured": bool(os.getenv("REDIS_URL", "").strip()),
            "rq_worker": "python -m backend.app.tasks.worker",
        },
        "database": get_database_health(),
        "dr": collect_dr_status(db_path),
    }
