# إعداد Railway الكامل — كل الخطوات

الإنتاج: `https://baupass-production.up.railway.app`

## 1) خدمة API (موجودة)

| متغير | القيمة |
|--------|--------|
| `BAUPASS_PG_RUNTIME` | `0` |
| `BAUPASS_DB_PATH` | `/data/baupass.db` |
| `BAUPASS_ALLOW_SQLITE_PRODUCTION` | `1` |
| `BAUPASS_SECRET_KEY` | عشوائي طويل |
| `BAUPASS_AUDIT_SIGNING_KEY` | عشوائي طويل |
| Volume | mount `/data` |

**لا** تضع `DATABASE_URL` على خدمة API حتى تكتمل ترحيل PostgreSQL.

## 2) Redis (موصى به)

1. Railway → **New** → **Database** → **Redis**
2. على خدمة API: **Variables** → **Reference** → `REDIS_URL`
3. أضف:

```env
BAUPASS_DAILY_JOBS_MODE=rq
BAUPASS_INVOICE_RETRY_MODE=rq
BAUPASS_DUNNING_MODE=rq
BAUPASS_WORKER_SESSION_CLEANUP_MODE=rq
```

## 3) خدمة Worker (ثانية)

1. **New Service** → نفس المستودع / Dockerfile
2. **Start Command:** `python -m backend.app.tasks.worker`
3. نفس `REDIS_URL` (Reference) + نفس `BAUPASS_DB_PATH` + Volume `/data` (أو نفس المشروع)

## 4) تطبيق الموظف

```env
BAUPASS_WORKER_APK_URL=https://.../app-release.apk
# BAUPASS_TESTFLIGHT_URL=https://testflight.apple.com/join/...
```

بعد GitHub Actions build للـ APK.

## 5) AI (Enterprise)

```env
OPENAI_API_KEY=sk-...
BAUPASS_AI_MODEL=gpt-4o-mini
```

## 6) تحقق بعد النشر

```powershell
$env:PUBLIC_BASE_URL = "https://baupass-production.up.railway.app"
powershell -ExecutionPolicy Bypass -File .\deploy\railway-health-check.ps1
```

يجب أن يمر:

- `/api/health/ready` → ready
- `/enterprise-hub.html` → 200
- `/api/platform/enterprise-catalog/preview` → layerCount 16

## 7) واجهات Admin

| الرابط | المحتوى |
|--------|---------|
| `/admin` | Admin v2 — تبويب **المؤسسة** + **Geofence·أتمتة·تكامل** |
| `/enterprise-hub.html` | 16 طبقة + خطط |
| `/ops-command-center.html` | مركز العمليات |

## 8) اختبار ميداني

`docs/field-test-checklist-AR.md`
