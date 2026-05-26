# Railway — إعداد الإنتاج (Volume + Redis + اختياري PostgreSQL)

## 1. الخدمة الرئيسية (API + PWA)

### Volume (إلزامي)

1. Service → **Volumes** → Create  
2. Mount path: **`/data`**  
3. لا تحذف Volume عند redeploy  

### متغيرات البيئة

انسخ من `.env.railway.example` إلى Railway → **Variables**.

الحد الأدنى:

```env
PUBLIC_BASE_URL=https://baupass-production.up.railway.app
BAUPASS_DB_PATH=/data/baupass.db
BAUPASS_BACKUP_ON_BOOT=1
BAUPASS_SECRET_KEY=<64 hex chars>
BAUPASS_AUDIT_SIGNING_KEY=<64 hex chars>
BAUPASS_IMMUTABLE_AUDIT=1
BAUPASS_ENABLE_HSTS=1
```

### التحقق

```http
GET https://YOUR-DOMAIN/api/health
```

توقّع:

```json
{
  "checks": {
    "database": { "persistent": true, ... },
    "redis": { "status": "ok" }
  }
}
```

---

## 2. Redis (موصى به بشدة)

### إنشاء Redis على Railway

1. في نفس المشروع: **+ New** → **Database** → **Redis**  
2. في خدمة **baupass API**: **Variables** → **Add Reference**  
3. اختر `REDIS_URL` من خدمة Redis  

أو يدوياً:

```env
REDIS_URL=redis://default:PASSWORD@redis.railway.internal:6379
```

### تفعيل RQ (بدل threads)

```env
BAUPASS_DAILY_JOBS_MODE=rq
BAUPASS_INVOICE_RETRY_MODE=rq
BAUPASS_DUNNING_MODE=rq
BAUPASS_WORKER_SESSION_CLEANUP_MODE=rq
```

### خدمة Worker (ثانية)

| Field | Value |
|-------|--------|
| Source | نفس repo + branch `main` |
| Start Command | `python -m backend.app.tasks.worker` |
| Variables | نفس `REDIS_URL`, `BAUPASS_DB_PATH`, secrets |

بدون worker: المهام تعود تلقائياً إلى **thread** (أبطأ وأقل استقراراً مع عدة replicas).

### التحقق

```http
GET https://YOUR-DOMAIN/api/health/queues
```

---

## 3. PostgreSQL (مرحلة لاحقة — اختياري)

**اليوم:** ابقوا على SQLite + `/data` — كافٍ للسوق الأول.

**عند النمو:**

1. Railway → **PostgreSQL**  
2. `DATABASE_URL=${{Postgres.DATABASE_URL}}`  
3. `BAUPASS_ALLOW_SQLITE_PRODUCTION=0` (بعد اختبار staging)  
4. تشغيل:

```bash
python backend/ops/postgres_preflight.py
python -m backend.app.migrations.runner --migrate
```

5. `/api/health` → `database.backend: postgres`

راجع: [postgres-runtime-cutover.md](./postgres-runtime-cutover.md)

---

## 4. مراقبة (اختياري)

```env
SENTRY_DSN=https://...
SENTRY_ENVIRONMENT=production
BAUPASS_STRUCTURED_LOGS=1
```

Prometheus: scrape `https://YOUR-DOMAIN/metrics` (Grafana Cloud أو self-hosted).

---

## 5. Web Push (Worker PWA)

```env
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_EMAIL=mailto:admin@your-domain.de
```

---

## 6. مشاكل شائعة

| المشكلة | الحل |
|---------|------|
| بيانات تختفي بعد deploy | Volume `/data` + `persistent: true` |
| `redis: unavailable` | أضف Redis + `REDIS_URL` |
| فواتير بطيئة | RQ worker + `BAUPASS_INVOICE_RETRY_MODE=rq` |
| `ERR_TIMED_OUT` بعد deploy | انتظر 1–2 دقيقة (إعادة تشغيل الحاوية) |
| أيقونة PWA خاطئة | بدون `?v=` في manifest |

---

## 7. سكربت فحص سريع (محلي)

```powershell
cd C:\Users\u4363\Desktop\baustelle
$base = "https://baupass-production.up.railway.app"
Invoke-RestMethod "$base/api/health"
Invoke-RestMethod "$base/api/health/queues"
Invoke-RestMethod "$base/api/v1/public/health"
```
