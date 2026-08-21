"""
Compute high-availability posture for operators and capabilities API.

Target for ≥95%: Postgres runtime + Redis + dedicated RQ worker + ≥2 web
replicas + object storage (S3) so /data is not the media SPOF + DR ok.
"""
from __future__ import annotations

import os
from typing import Any


def object_storage_status() -> dict[str, Any]:
    backend = (os.getenv("UPLOAD_BACKEND") or os.getenv("BAUPASS_OBJECT_STORAGE") or "local").strip().lower()
    s3_bucket = (os.getenv("S3_BUCKET") or "").strip()
    s3_ready = backend in {"s3", "r2", "minio"} and bool(s3_bucket)
    return {
        "backend": "s3" if s3_ready else ("s3_misconfigured" if backend in {"s3", "r2", "minio"} else "local"),
        "s3Configured": s3_ready,
        "bucketSet": bool(s3_bucket),
        "mediaSpofOnVolume": not s3_ready,
        "hint": "Set UPLOAD_BACKEND=s3 and S3_BUCKET to move media off /data volume.",
    }


def _replica_count() -> int:
    raw = os.getenv("BAUPASS_WEB_REPLICAS") or os.getenv("SUPPIX_WEB_REPLICAS") or "1"
    try:
        return max(1, int(str(raw).strip()))
    except ValueError:
        return 1


def _dedicated_worker() -> bool:
    embed = (os.getenv("SUPPIX_EMBED_RQ_WORKER") or os.getenv("BAUPASS_EMBED_RQ_WORKER") or "0").strip().lower()
    embedded = embed in {"1", "true", "yes", "on"}
    redis = bool((os.getenv("REDIS_URL") or "").strip())
    # Dedicated worker = Redis present and embed worker disabled (separate service).
    return redis and not embedded


def collect_ha_posture() -> dict[str, Any]:
    from backend.app.db.runtime import postgres_runtime_enabled
    from backend.app.tasks import task_queues_ready

    postgres = postgres_runtime_enabled()
    redis = bool((os.getenv("REDIS_URL") or "").strip())
    queues = bool(task_queues_ready())
    replicas = _replica_count()
    worker = _dedicated_worker()
    storage = object_storage_status()
    pg_required = (os.getenv("SUPPIX_PG_REQUIRED") or os.getenv("BAUPASS_PG_REQUIRED") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    checks = {
        "postgresRuntime": postgres,
        "postgresRequired": pg_required,
        "redisConfigured": redis,
        "taskQueuesReady": queues,
        "dedicatedRqWorker": worker,
        "webReplicasAtLeast2": replicas >= 2,
        "objectStorageOffVolume": bool(storage.get("s3Configured")),
        "sqliteReplicaUnsafe": not postgres,
    }

    # Weight toward dual-replica production posture (max 100).
    score = 0
    if postgres:
        score += 30
    if redis and queues:
        score += 20
    if worker:
        score += 15
    if replicas >= 2 and postgres:
        score += 20
    elif replicas >= 2 and not postgres:
        score += 0  # unsafe; do not credit
    if storage.get("s3Configured"):
        score += 10
    if pg_required and postgres:
        score += 5

    if not postgres:
        level = "sqlite_single_node"
    elif score >= 95:
        level = "ha_production"
    elif score >= 70:
        level = "ha_ready"
    elif score >= 45:
        level = "ha_partial"
    else:
        level = "ha_bootstrap"

    next_steps: list[str] = []
    if not postgres:
        next_steps.append("Cut over DATABASE_URL + SUPPIX_PG_RUNTIME=1 (see docs/ops/railway-ha-cutover.md).")
    if not redis:
        next_steps.append("Attach REDIS_URL and run a dedicated RQ worker service.")
    elif not worker:
        next_steps.append("Set SUPPIX_EMBED_RQ_WORKER=0 and deploy python -m backend.app.tasks.worker.")
    if postgres and replicas < 2:
        next_steps.append("Scale web replicas to 2 and set SUPPIX_WEB_REPLICAS=2.")
    if not storage.get("s3Configured"):
        next_steps.append("Configure UPLOAD_BACKEND=s3 + S3_BUCKET to remove /data media SPOF.")
    if postgres and not pg_required:
        next_steps.append("After stability set SUPPIX_PG_REQUIRED=1.")

    return {
        "score": min(100, score),
        "level": level,
        "checks": checks,
        "configuredWebReplicas": replicas,
        "recommendedWebReplicas": 2 if postgres and redis else 1,
        "objectStorage": storage,
        "nextSteps": next_steps,
        "cutoverGuide": "docs/ops/railway-ha-cutover.md",
        "drSnapshotScript": "backend/ops/postgres_dr_snapshot.py --dump",
    }
