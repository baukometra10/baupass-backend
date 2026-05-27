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
powershell -ExecutionPolicy Bypass -File .\deploy\railway-complete-setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\field-test.ps1
```

أو API مباشرة: `GET /api/platform/setup-status` — يعرض ما ينقص من المتغيرات.

## 7) Demo Enterprise (اختياري)

```env
BAUPASS_SEED_DEMO_ENTERPRISE=1
```

يفعّل خطة `enterprise` لشركات Demo عند الإقلاع.

## 8) Sentry + Stripe (اختياري)

```env
SENTRY_DSN=https://...
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

راجع: `docs/stripe-live-setup.md`

## 9) واجهات Admin

| الرابط | المحتوى |
|--------|---------|
| `/admin` | Admin v2 — تبويب **المؤسسة** + **Geofence·أتمتة·تكامل** |
| `/enterprise-hub.html` | 16 طبقة + خطط |
| `/ops-command-center.html` | مركز العمليات |

## 10) اختبار ميداني

- `docs/field-test-checklist-AR.md`
- `docs/onboarding-1page-DE.md` / `docs/onboarding-1page-AR.md`
- `scripts/field-test.ps1`

## 11) PostgreSQL (لاحقاً)

`docs/postgres-cutover-runbook.md`
