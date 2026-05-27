# إكمال الإنتاج — كل ما يمكن بدون تقسيم Domains

> **مؤجّل لاحقاً:** نقل `server.py` إلى domains (البنود 1–3). باقي المنصة جاهزة في الكود.

## Railway — متغيرات كاملة

```env
# Core
PUBLIC_BASE_URL=https://YOUR_APP.up.railway.app
BAUPASS_SECRET_KEY=...
BAUPASS_DB_PATH=/data/baupass.db

# PostgreSQL (بعد الاستقرار)
DATABASE_URL=${{Postgres.DATABASE_URL}}
BAUPASS_PG_RUNTIME=1
BAUPASS_PG_AUTO_BOOTSTRAP=1
BAUPASS_PG_BOOTSTRAP_SQLITE_PATH=/data/baupass.db
# BAUPASS_PG_REQUIRED=1

# Redis + Worker
REDIS_URL=${{Redis.REDIS_URL}}
# خدمة ثانية: python -m backend.app.tasks.worker

# Hybrid worker app
BAUPASS_WORKER_APK_URL=https://.../app-release.apk
BAUPASS_TESTFLIGHT_URL=

# Observability
SENTRY_DSN=
BAUPASS_OTEL=1
OTEL_EXPORTER_OTLP_ENDPOINT=
BAUPASS_LOG_FORWARD_URL=
BAUPASS_LOG_FORWARD_TOKEN=

# DR / Archive
BAUPASS_BACKUP_ON_BOOT=1
BAUPASS_ARCHIVE_ACCESS_LOGS_ON_BOOT=0
BAUPASS_ACCESS_LOG_RETENTION_DAYS=365
BAUPASS_DR_STRICT=0

# WebSocket
BAUPASS_WEBSOCKET_ENABLED=1
BAUPASS_WEBSOCKET_REQUIRE_SESSION=1

# Security
BAUPASS_FIELD_ENCRYPTION_KEY=
BAUPASS_ZERO_TRUST=0
BAUPASS_ZERO_TRUST_DEVICE_BINDING=0

# Multi-region (scaffold)
BAUPASS_REGION=eu-west
BAUPASS_REGION_STRATEGY=single
```

## Migrations

```bash
python -m backend.app.migrations.runner --migrate
```

## تحقق

```powershell
.\deploy\railway-health-check.ps1
python backend/ops/production_cutover_check.py --base-url https://YOUR_APP.up.railway.app
```

## Hybrid Worker — 3 أوضاع

1. App: `/api/worker-app/login` (PWA + Flutter)
2. Gate reader NFC/RFID: `/api/scan`
3. HCE: `/api/worker-app/hce`

توزيع: `GET /api/v2/mobile/distribution`

## API جديدة (عمليات)

- `GET /api/operations/intelligence/optimization`
- `GET /api/operations/intelligence/allocation`
- `GET /api/operations/intelligence/scheduling`
- `GET /api/operations/intelligence/forecast`
- `GET /api/platform/global-readiness`
- `GET /api/marketplace/plugins/sandbox-policy`
