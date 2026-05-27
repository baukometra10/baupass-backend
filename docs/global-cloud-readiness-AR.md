# الجاهزية السحابية العالمية — BauPass

## الهدف

منصة **مستقرة وسريعة** على السحابة، جاهزة لأي بلد وأي تطوير لاحق — قبل تنفيذ قائمة الميزات الكبيرة.

## ما يوفره النظام الآن

| الطبقة | الوظيفة |
|--------|---------|
| **ProxyFix** | HTTPS خلف Railway / CDN |
| **Redis** | Rate limiting موزّع + مهام خلفية (RQ) |
| **SQLite + Volume** | بيانات دائمة على `/data` |
| **Edge middleware** | API بدون cache؛ ملفات ثابتة + PWA بذاكرة cache مناسبة |
| **Event bus** | تأثيرات جانبية غير متزامنة (سرعة البوابة) |
| **Health** | `/api/health`, `/ready`, `/queues`, `/api/v1/public/health` |
| **Blueprints معزولة** | فشل جزء لا يوقف المنصة |
| **Docker** | Python 3.11 — مناسب للإنتاج العالمي |

## متغيرات الإنتاج (Railway)

```env
PUBLIC_BASE_URL=https://your-app.up.railway.app
BAUPASS_DB_PATH=/data/baupass.db
BAUPASS_BACKUP_ON_BOOT=1
REDIS_URL=redis://...
BAUPASS_DAILY_JOBS_MODE=rq
BAUPASS_PLATFORM_ENABLED=1

# عالمي (اختياري)
BAUPASS_DEFAULT_TIMEZONE=UTC
BAUPASS_REGION=eu-west
BAUPASS_CDN_CACHE_SECONDS=86400
BAUPASS_PWA_SHELL_CACHE_SECONDS=300
# BAUPASS_REQUIRE_REDIS=1   # فقط إذا أردت أن /ready يفشل بدون Redis
```

خدمة ثانية للـ worker:

```bash
python -m backend.app.tasks.worker
```

## التحقق بعد النشر

```powershell
.\deploy\railway-health-check.ps1 -BaseUrl "https://your-app.up.railway.app"
```

أو يدوياً:

- `GET /api/health` → `status: ok`, `db.persistent: true`, `cloud.provider`
- `GET /api/health/ready` → `status: ready`
- `GET /api/health/queues` → `ready: true` (مع Redis + worker)

## توسع عالمي (مراحل لاحقة — ليست مطلوبة اليوم)

1. **منطقة واحدة قوية** (Railway EU أو US) + CDN أمام الملفات الثابتة
2. **PostgreSQL** عند نمو البيانات (`DATABASE_URL`)
3. **مناطق متعددة** — قراءة محلية + كتابة مركزية (بعد PostgreSQL)

## قبل إرسال القائمة الكبيرة

بعد نشر هذا الإصدار وتأكيد Health أعلاه، أرسل قائمة الميزات — ننفّذها فوق أساس مستقر.
