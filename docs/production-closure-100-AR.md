# إغلاق الإنتاج — PostgreSQL + Replica + DR + Multi-Region

هذه الوثيقة تكمّل `docs/postgres-cutover-steps-AR.md` و`docs/multi-region-readiness-AR.md`.

## 1) PostgreSQL — التفعيل النهائي على Railway

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
BAUPASS_PG_RUNTIME=1
BAUPASS_PG_AUTO_BOOTSTRAP=1
BAUPASS_PG_BOOTSTRAP_SQLITE_PATH=/data/baupass.db
BAUPASS_DB_PATH=/data/baupass.db
```

بعد أسبوع استقرار بدون أخطاء:

```env
BAUPASS_PG_REQUIRED=1
```

## 2) Read Replica (اختياري)

```env
DATABASE_READ_REPLICA_URL=${{Postgres-Replica.DATABASE_URL}}
DB_READ_POOL_MIN_SIZE=2
DB_READ_POOL_MAX_SIZE=16
```

المسارات التي تستخدم القراءة من Replica:

- `/api/analytics/workforce-heatmap`
- `/api/contractors/intelligence`
- `/api/compliance/expiry-predictions`
- `/api/dashboard/live`

## 3) Disaster Recovery

### فحص HTTP

```http
GET /api/health/dr
```

يعيد حالة النسخ الاحتياطي (SQLite على `/data`) + صحة PostgreSQL + Replica عند التفعيل.

### متغيرات DR

```env
BAUPASS_DR_MAX_BACKUP_AGE_HOURS=48
BAUPASS_DR_REQUIRE_REPLICA=0
```

### أوامر Ops

```bash
# SQLite backup + verify
python backend/ops/db_backup.py backup --db-path /data/baupass.db --backup-dir /data/backups

# PostgreSQL table counts (+ pg_dump إن وُجد)
python backend/ops/postgres_dr_snapshot.py
python backend/ops/postgres_dr_snapshot.py --dump

# فحص cutover كامل ضد URL الإنتاج
python backend/ops/production_cutover_check.py --base-url https://YOUR_APP.up.railway.app
```

## 4) Multi-Region (مرحلة scaffold)

```env
BAUPASS_REGION=eu-west
BAUPASS_REGION_STRATEGY=multi
BAUPASS_ACTIVE_REGIONS=eu-west,eu-central
```

`/api/health/ready` يتحقق من أن المنطقة الحالية ضمن `BAUPASS_ACTIVE_REGIONS`.

**ملاحظة:** النشر متعدد المناطق مع replication حقيقي للبيانات يتطلب بنية Railway/K8s إضافية — الكود جاهز للفحص والتوجيه، وليس نشراً عالمياً كاملاً بعد.

## 5) قائمة تحقق سريعة

| الخطوة | الأمر / Endpoint |
|--------|------------------|
| حي | `GET /api/health/live` |
| جاهز | `GET /api/health/ready` |
| قاعدة بيانات | `GET /api/health` |
| DR | `GET /api/health/dr` |
| طوابير | `GET /api/health/queues` |
| Cutover script | `production_cutover_check.py` |

## 6) Worker PWA (ليس تطبيقاً أصلياً)

تطبيق العامل = `emp-app.html` + `worker-app.js` (PWA). تطبيقات iOS/Android الأصلية خارج النطاق ما لم يُطلب صراحة.
