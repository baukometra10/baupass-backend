# Staging على Railway — خدمة ثانية

هذا الدليل يصف **بيئة Staging** منفصلة عن الإنتاج (`baupass-production`) دون قطع قاعدة البيانات الحالية.

## لماذا خدمة ثانية؟

| البيئة | الغرض |
|--------|--------|
| **Production** | عملاء حقيقيون، SQLite/Postgres إنتاج، `BAUPASS_DEMO_MODE=0` |
| **Staging** | اختبار نشر، Admin v2، APK، Postgres تجريبي |

## Checklist — إنشاء Staging

1. **مشروع Railway جديد** أو **Service ثانٍ** في نفس المشروع (يفضّل مشروع منفصل للعزل).
2. **نفس المستودع** `baupass-backend`، فرع `main`، Root: `backend`، Start: `python run_prod.py`.
3. **متغيرات لا تُنسخ أعمى من الإنتاج:**
   - `BAUPASS_DEMO_MODE=0` (أو `1` فقط لعرض تجريبي داخلي)
   - `SECRET_KEY` **جديد** (لا تستخدم مفتاح الإنتاج)
   - `DATABASE_URL` فارغ → SQLite على Volume **خاص بـ Staging**، أو Postgres Staging منفصل
   - `PUBLIC_BASE_URL` = رابط Staging (مثل `https://baupass-staging.up.railway.app`)
   - `BAUPASS_WORKER_APK_URL` = APK يشير إلى Staging (ليس إنتاج)
4. **Volume** لـ `/data` إذا SQLite — **لا تشارك** Volume الإنتاج.
5. **Health check:** `GET /api/health` و `GET /api/ready` (Railway → Settings → Health).
6. **GitHub Actions (اختياري):** workflow منفصل أو `environment: staging` مع `PUBLIC_BASE_URL` لـ Staging.

## بعد النشر

```powershell
$env:PUBLIC_BASE_URL = "https://YOUR-STAGING.up.railway.app"
python backend/ops/validate_enterprise_env.py --live-only
python backend/ops/e2e_production_smoke.py
```

أضف في GitHub (Environment `staging`):

- `PUBLIC_BASE_URL`
- `BAUPASS_SMOKE_TOKEN` (مستخدم اختبار فقط)

## Postgres على Staging فقط

1. أضف Postgres plugin على **خدمة Staging فقط**.
2. `DATABASE_URL` من Railway → Staging service.
3. شغّل `python backend/ops/sqlite_to_postgres.py` **ضد Staging** قبل الإنتاج.
4. راقب 7 أيام smoke على Staging، ثم خطّة cutover للإنتاج (`docs/postgres-cutover-steps-AR.md`).

## ما لا تفعله على Staging

- لا تربط `BAUPASS_WORKER_APK_URL` الإنتاجي بتطبيق يشير إلى Staging بالخطأ (والعكس).
- لا تشغّل `postgres_cutover` على قاعدة الإنتاج من CI Staging.
- لا تفعّل webhooks فواتير/Slack الإنتاجية إلا بقنوات اختبار.

## روابط

- [Smoke token و APK](smoke-token-and-apk-AR.md)
- [استقرار المنصة](platform-phases-stability-AR.md)
- [Postgres cutover](postgres-cutover-steps-AR.md)
