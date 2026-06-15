# استقرار البنية — ما تم إصلاحه

## الهدف

قبل أي ميزات جديدة: **استقرار + سرعة + بنية قوية** دون كسر الـ API الحالي (`/api/*`).

## التغييرات التقنية

### 1. تسجيل الـ Blueprints (عزل الأخطاء)

- `backend/app/api/blueprint_registry.py`: كل مجموعة (`worker_app`, `domains`, `platform`) تُسجَّل بشكل مستقل.
- فشل منصة واحدة **لا يوقف** التطبيق الأساسي.
- الحالة تظهر في `/api/health` تحت `architecture.modularBlueprints`.

### 2. طبقة المنصة (اختيارية وآمنة)

- `BAUPASS_PLATFORM_ENABLED=0` لتعطيل المنصة بالكامل عند الحاجة.
- كل خطوة (Sentry, metrics, SocketIO, AI, …) في `try/except` منفصل.
- Prometheus: إذا لم يُثبَّت `prometheus_client`، `/metrics` يعيد 503 بدلاً من تعطيل الإقلاع.

### 3. سرعة مسار البوابة (Event bus)

- `publish_event`: حفظ SQLite متزامن فقط.
- Redis / Webhooks / Automation في **خيط خلفي** — لا يبطئ تسجيل الحضور عند البوابة.

### 4. SQLite (أداء + استقرار)

- `backend/app/core/sqlite_pragmas.py`: WAL, cache, mmap, foreign_keys, busy_timeout.
- `get_db()` في `server.py` يستخدم نفس الإعدادات.
- متغيرات: `BAUPASS_SQLITE_CACHE_KB`, `BAUPASS_SQLITE_MMAP_MB`, `BAUPASS_SQLITE_BUSY_TIMEOUT_MS`.

### 5. Migrations على الإقلاع

- `entrypoint.py --mode prod` يطبّق migrations بعد `init_db()` (Railway).
- `runtime_bootstrap` يطبّقها أيضاً عند تحميل `server.py`.

### 6. إصلاح domain billing

- استعلام الفواتير يستخدم أعمدة موجودة (`invoice_period` بدلاً من `due_date` غير الموجود).

## التحقق على Railway (5 دقائق)

1. Volume: `BAUPASS_DB_PATH=/data/baupass.db`
2. `GET /api/health` → `db.persistent: true`, `status: ok`
3. `GET /api/health` → `architecture.modularBlueprints` كلها `ok` (أو تعرف أي مجموعة فشلت)
4. `GET /observability/status` (اختياري)
5. اختبار بوابة سريع: زمن استجابة `/api/gate/tap` بدون تأخير ملحوظ

## ما لم يُغيَّر (عمداً)

- `server.py` يبقى مصدر الحقيقة للـ API القديم.
- لا PostgreSQL إجباري في المرحلة 1.
- لا تطبيقات iOS/Android — Worker PWA فقط.

## إذا تعطّل الإقلاع

```env
BAUPASS_PLATFORM_ENABLED=0
```

ثم أعد النشر وافحص السجلات لمعرفة المكوّن الذي فشل.

## الجاهزية العالمية

راجع [`global-cloud-readiness-AR.md`](global-cloud-readiness-AR.md) لمتغيرات السحابة والتحقق بعد النشر.
