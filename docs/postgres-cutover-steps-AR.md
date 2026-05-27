# PostgreSQL — خطوات التفعيل (مرحلة 2)

## الوضع الحالي

| المكوّن | الحالة |
|---------|--------|
| Connection pool (`psycopg_pool`) | ✅ |
| `get_db()` عبر PostgreSQL | ✅ عند `BAUPASS_PG_RUNTIME=1` |
| نقل البيانات | سكربت `backend/ops/sqlite_to_postgres.py` |
| الإنتاج الافتراضي | **SQLite على `/data`** (آمن) |

## الخطوات

### 1) إنشاء PostgreSQL على Railway

- أضف خدمة **PostgreSQL**
- انسخ `DATABASE_URL` إلى خدمة API

### 2) Preflight

```bash
set DATABASE_URL=postgresql://...
python backend/ops/postgres_preflight.py
```

يجب أن يظهر `status: ok`.

### 3) نقل البيانات من SQLite

```bash
python backend/ops/sqlite_to_postgres.py --sqlite /data/baupass.db --truncate
```

أو محلياً:

```bash
python backend/ops/sqlite_to_postgres.py --sqlite backend/baupass.db --truncate
```

### 4) تفعيل Runtime

في Railway Variables:

```env
DATABASE_URL=postgresql://...
BAUPASS_PG_RUNTIME=1
BAUPASS_ALLOW_SQLITE_PRODUCTION=1
```

`BAUPASS_ALLOW_SQLITE_PRODUCTION=1` للتراجع السريع (أزلها لاحقاً عند الثقة الكاملة).

### 5) Redis + Worker (موصى به)

```env
REDIS_URL=redis://...
BAUPASS_DAILY_JOBS_MODE=rq
```

خدمة ثانية: `python -m backend.app.tasks.worker`

### 6) التحقق

```powershell
.\deploy\railway-health-check.ps1 -BaseUrl "https://your-app.up.railway.app"
```

- `/api/health` → `db.backend: postgres`
- `/api/health/ready` → `ready`

## التراجع

1. أزل `BAUPASS_PG_RUNTIME` أو ضعه `0`
2. أعد النشر — يعود إلى SQLite على `/data`
3. البيانات على Volume لم تُمس

## ملاحظات

- بعض استعلامات SQLite النادرة قد تحتاج تعديلاً يدوياً على PG.
- بعد أسبوع مستقر: أزل `BAUPASS_ALLOW_SQLITE_PRODUCTION` واعتمد PG فقط.
