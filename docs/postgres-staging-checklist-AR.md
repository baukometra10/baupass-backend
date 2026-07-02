# PostgreSQL — Staging Checklist (قائمة Staging)

> **الهدف:** تشغيل نسخة Staging على PostgreSQL **قبل** تفعيل `BAUPASS_PG_RUNTIME=1` في الإنتاج.

**المرجع:** [`postgres-cutover-runbook.md`](postgres-cutover-runbook.md) · [`postgres-cutover-steps-AR.md`](postgres-cutover-steps-AR.md)

---

## المرحلة 0 — التحضير

- [ ] نسخة Staging منفصلة على Railway (خدمة API + Volume SQLite للنسخ الاحتياطي)
- [ ] خدمة **PostgreSQL** على Railway (Staging)
- [ ] **Redis** على Staging (للـ rate limit + RQ)
- [ ] نسخ احتياطي: `cp /data/baupass.db /data/baupass.db.bak-YYYYMMDD`

---

## المرحلة 1 — المتغيرات (Staging فقط)

```env
PUBLIC_BASE_URL=https://YOUR-STAGING.up.railway.app
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
BAUPASS_SECRET_KEY=<32+ chars>
BAUPASS_AUDIT_SIGNING_KEY=<secret>
BAUPASS_FIELD_ENCRYPTION_KEY=<secret>
BAUPASS_RTSP_BRIDGE_TOKEN=<secret>
BAUPASS_DAILY_JOBS_MODE=rq
BAUPASS_PG_AUTO_BOOTSTRAP=1
# لا تفعّل بعد:
# BAUPASS_PG_RUNTIME=0
```

- [ ] **لا** `BAUPASS_ALLOW_DEMO=1` على Staging ما لم يكن مقصوداً
- [ ] Volume `/data` ما زال موجوداً للتراجع

---

## المرحلة 2 — Preflight

```powershell
cd C:\Users\u4363\Desktop\baustelle
$env:DATABASE_URL = "postgresql://..."
python backend/ops/postgres_preflight.py
```

**متوقع:** `"status": "ok"`

- [ ] Preflight OK
- [ ] `psycopg` و `psycopg_pool` مثبتان (`pip install -r backend/requirements.txt`)

---

## المرحلة 3 — Schema + نقل البيانات

```powershell
# على Staging shell أو محلياً مع DATABASE_URL
python backend/ops/sqlite_to_postgres.py --sqlite /data/baupass.db --truncate
```

- [ ] Migrations طُبّقت على PostgreSQL
- [ ] عدد الشركات/العمال في PG ≈ SQLite
- [ ] لا أخطاء FK أثناء النقل

**تحقق سريع:**

```sql
SELECT COUNT(*) FROM companies;
SELECT COUNT(*) FROM workers WHERE deleted_at IS NULL;
SELECT COUNT(*) FROM site_cameras;
```

---

## المرحلة 4 — تفعيل Runtime (Staging)

```env
BAUPASS_PG_RUNTIME=1
BAUPASS_ALLOW_SQLITE_PRODUCTION=1
```

أعد تشغيل خدمة API.

- [ ] `GET /api/health/ready` → 200
- [ ] `GET /api/health` → `"database": { "backend": "postgres", "status": "ok" }`
- [ ] `GET /api/platform/database-status` (superadmin) → pool stats

**سكربت Windows:**

```powershell
.\deploy\postgres-staging-verify.ps1 -BaseUrl "https://YOUR-STAGING.up.railway.app"
```

---

## المرحلة 5 — اختبار وظيفي (Smoke)

| # | السيناريو | OK |
|---|-----------|-----|
| 1 | Login superadmin + company-admin | ☐ |
| 2 | قائمة workers + worker واحد | ☐ |
| 3 | Check-in / check-out (turnstile) | ☐ |
| 4 | طلب إجازة + موافقة/رفض | ☐ |
| 5 | Chat: رسالة admin ↔ worker | ☐ |
| 6 | Kameras: bulk import + snapshot | ☐ |
| 7 | RTSP ingest heartbeat (agent) | ☐ |
| 8 | PDF report / invoice list | ☐ |
| 9 | Worker app session login | ☐ |
| 10 | `npm run test:e2e:platform` ضد Staging URL | ☐ |

---

## المرحلة 6 — Worker + Jobs

- [ ] خدمة ثانية: `python -m backend.app.tasks.worker`
- [ ] `GET /api/health/queues` → workers active ≥ 1
- [ ] Daily jobs / camera digest / FCM لا تفشل في logs

---

## المرحلة 7 — Go/No-Go للإنتاج

- [ ] Staging مستقر **≥ 48 ساعة**
- [ ] لا regressions في pytest: `pytest backend/tests`
- [ ] Rollback مُختبر: `BAUPASS_PG_RUNTIME=0` + SQLite volume
- [ ] إزالة `BAUPASS_ALLOW_SQLITE_PRODUCTION` بعد الثقة الكاملة

---

## Rollback (طوارئ)

1. `BAUPASS_PG_RUNTIME=0`
2. أعد تشغيل API (يقرأ `/data/baupass.db`)
3. تحقق: `/api/health/ready`
4. لا تحذف Volume SQLite حتى اكتمال PG

---

## بعد الإنتاج

- [ ] Read replica (اختياري): `DATABASE_READ_REPLICA_URL`
- [ ] مراقبة: Sentry + Grafana (`deploy/grafana/`)
- [ ] نسخ احتياطي PG: `backend/ops/postgres_dr_snapshot.py`

---

*آخر تحديث: يونيو 2026*
