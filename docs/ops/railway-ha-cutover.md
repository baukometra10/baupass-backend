# Railway HA cutover (Postgres + dual web + Redis worker)

Goal: remove SQLite/`/data` single-node risk and reach dual-replica safe HA.

## Prerequisites

1. Railway Postgres plugin → `DATABASE_URL`
2. Railway Redis → `REDIS_URL`
3. Maintenance window (short write freeze recommended for first migrate)

## Steps

1. Preflight:
   ```bash
   python backend/ops/postgres_preflight.py
   ```
2. Migrate data (from a controlled copy of `/data/baupass.db`):
   ```bash
   python backend/ops/sqlite_to_postgres.py --sqlite /data/baupass.db --truncate
   ```
3. API service env:
   - `SUPPIX_PG_RUNTIME=1`
   - `SUPPIX_PG_REQUIRED=0` (flip to `1` after soak)
   - `SUPPIX_EMBED_RQ_WORKER=0`
   - `SUPPIX_WEB_REPLICAS=2`
   - `DB_POOL_MAX_SIZE=20`–`40`
4. Add worker service start command:
   ```bash
   python -m backend.app.tasks.worker
   ```
5. Object storage (remove media SPOF on volume):
   - `UPLOAD_BACKEND=s3`
   - `S3_BUCKET=…` (+ endpoint/keys for R2/MinIO/AWS)
6. Scale web replicas to **2** only after Postgres is live.
7. Verify:
   - `GET /api/health/ready`
   - `GET /api/health/queues`
   - `GET /api/health/dr`
   - `GET /api/platform/capabilities` → `ha.score` ≥ 95 when all checks pass
8. Optional scheduled dumps: `BAUPASS_PG_DR_SNAPSHOT_SCHEDULE=1`

## Never

- Do not set web replicas > 1 while runtime is still SQLite.
- Do not delete `/data` until `SUPPIX_PG_REQUIRED=1` and backups are verified.
