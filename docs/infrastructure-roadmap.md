# BauPass – خريطة طريق البنية التحتية الاحترافية
# Infrastructure Roadmap

## الوضع الحالي (نقطة الانطلاق)

| الجانب | الوضع الحالي | المشكلة |
|--------|-------------|---------|
| قاعدة البيانات | SQLite | بدون migrations رسمية |
| كود الباكند | `server.py` – 19,139 سطر | غير قابل للصيانة |
| Rate Limiting | In-memory Python dict | يفشل مع multiple workers |
| Background Jobs | Flask threads | نقطة انهيار واحدة |
| Tenant Isolation | `WHERE company_id = ?` فقط | بدون architectural enforcement |
| Security Headers | جزئية | بدون CSP/HSTS |
| Migrations | يدوي في `init_db()` | خطر فقدان بيانات |

---

## ما تم بناؤه الآن

### 1. نظام Migrations الاحترافي
**الملفات:**
- `backend/app/database.py` — `MigrationRunner` مع checksum verification
- `backend/app/migrations/__init__.py` — 8 migrations جاهزة
- `backend/app/migrations/runner.py` — CLI للتشغيل

**الاستخدام:**
```bash
# فحص حالة قاعدة البيانات
python -m backend.app.migrations.runner --status

# تطبيق migrations جديدة
python -m backend.app.migrations.runner --migrate

# معاينة بدون تطبيق
python -m backend.app.migrations.runner --dry-run
```

**Migrations المضمَّنة:**
- `001` — Bootstrap (نقطة البداية)
- `002` — 20+ index على الجداول الأساسية (أداء فوري)
- `003` — Immutable audit log enhancement (event_hash, chain integrity)
- `004` — Rate limit bans table
- `005` — Device trust + Anti-replay (used_nonces)
- `006` — Feature flags system
- `007` — Session management table
- `008` — GDPR compliance tables

---

### 2. Distributed Rate Limiting (Redis)
**الملف:** `backend/app/middleware/rate_limiting.py`

**يحل المشكلة:** Rate limiting الحالي في server.py يعمل بذاكرة Python process — لا يعمل مع Gunicorn أو Waitress بـ multiple workers.

**الميزات:**
- Sliding Window algorithm (Lua script atomic)
- Redis-based shared state عبر جميع workers
- Fallback تلقائي لـ in-memory إذا Redis غير متاح
- IP ban mechanism بعد تجاوز الحد
- Scopes مختلفة: auth_login / worker_api / gate_api / admin_api / global

**Scopes التلقائية:**
```python
"global":               (300,  60),   # 300 req/min
"auth_login":           (5,    300),  # 5 محاولات / 5 دقائق
"auth_login_fail":      (10,   900),  # lockout بعد 10 فشل
"worker_api":           (120,  60),
"gate_api":             (600,  60),   # البوابات تحتاج أكثر
```

---

### 3. Background Jobs Queue (RQ + Redis)
**الملفات:**
- `backend/app/tasks/__init__.py` — Queue manager + enqueue/enqueue_in
- `backend/app/tasks/email_tasks.py` — Email tasks مع idempotency
- `backend/app/tasks/worker.py` — Worker startup script

**تشغيل الـ Worker:**
```bash
python -m backend.app.tasks.worker
python -m backend.app.tasks.worker --queues critical high  # أولوية
python -m backend.app.tasks.worker --burst                  # انتهاء بعد إفراغ الـ queue
```

**الاستخدام في الكود:**
```python
from backend.app.tasks import enqueue
from backend.app.tasks.email_tasks import send_invoice_email

# بدل استدعاء مباشر (يحجب request):
# send_invoice_email(...)  ← خطأ

# استخدام queue:
enqueue("high", send_invoice_email,
    invoice_id=inv_id,
    company_email=email,
    # ...
)
```

---

### 4. Modular Architecture (App Factory)
**الملفات:**
- `backend/app/__init__.py` — Flask App Factory
- `backend/app/config.py` — بيئات متعددة (dev/test/prod)
- `backend/app/extensions.py` — Redis connection pool

---

### 5. Tenant Isolation Architecture
**الملف:** `backend/app/middleware/tenant.py`

```python
from backend.app.middleware.tenant import tenant_guard

def get_company_workers(company_id: int):
    tenant_guard(company_id)  # يُطلق PermissionError إذا غير مسموح
    return worker_repo.find_active()
```

---

### 6. Base Repository مع Tenant Isolation
**الملفات:**
- `backend/app/repositories/base.py` — BaseRepository
- `backend/app/repositories/worker_repo.py` — WorkerRepository مثال

```python
# كل query محمية تلقائياً بـ company_id
worker_repo = WorkerRepository()  # company_id من TenantContext
workers = worker_repo.find_active()  # SQL: WHERE company_id = ? AND status = 'active'
```

---

### 7. Security Middleware
**الملف:** `backend/app/middleware/security.py`

Headers تُضاف تلقائياً:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- `Content-Security-Policy: ...`
- `Referrer-Policy: strict-origin-when-cross-origin`

---

## خارطة الطريق: الخطوات التالية

### الأسبوع 1: تطبيق الـ Migrations
```bash
pip install redis rq
python -m backend.app.migrations.runner --dry-run
python -m backend.app.migrations.runner --migrate
```
**التأثير:** 20+ index → استعلامات أسرع 5-50x، tables للـ security events، sessions، GDPR.

---

### الأسبوع 2: تفعيل Redis Rate Limiting
1. في `backend/server.py`، استبدل `check_rate_limit()` تدريجياً:
```python
# بدل:
_rate_store[key] = ...  # in-memory

# استخدم:
from backend.app.extensions import get_redis
from backend.app.middleware.rate_limiting import RedisRateLimiter
```
2. شغّل Redis worker بجانب Flask.

---

### الأسبوع 3: نقل Background Jobs
كل مهمة في server.py تعمل في threads → انقلها إلى RQ:

```python
# ابحث في server.py عن:
threading.Thread(target=send_invoice_email, ...).start()
# ← استبدل بـ:
enqueue("high", send_invoice_email, ...)
```

---

### الأسبوع 4-8: تقسيم server.py
انقل بالترتيب التالي (من الأقل تأثيراً إلى الأكبر):

1. `/api/health` → `backend/app/api/health_routes.py` ✅ (تم)
2. `/api/public/*` → `backend/app/api/public.py`
3. `/api/auth/*` → `backend/app/api/auth.py` + `auth_service.py`
4. `/api/worker-app/*` → `backend/app/api/worker_app.py`
5. `/api/workers/*` → `backend/app/api/workers.py`
6. `/api/companies/*` → `backend/app/api/companies.py`
7. `/api/invoices/*` → `backend/app/api/invoices.py`
8. `/api/admin/*` → `backend/app/api/admin.py`

**لكل migration:**
```
server.py route → Blueprint route → Service method → Repository query
```

---

### الأسبوع 8-12: Security Architecture

#### Secret Management
```bash
# بدل hardcoded secrets:
# استخدم .env.local للتطوير
echo "BAUPASS_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" >> backend/.env.local
```

#### Field-Level Encryption للوثائق
```python
from cryptography.fernet import Fernet
# الـ key يُخزَّن في env var، البيانات في DB مشفَّرة
```

---

### الأسبوع 12-16: Observability

#### Structured Logging (جاهز جزئياً)
```python
# backend/app/middleware/logging_mw.py موجود
# يُضيف تلقائياً: request_id, duration, user_id, company_id
```

#### Metrics
```bash
pip install prometheus-flask-exporter
# يُعطي endpoint: /metrics لـ Grafana
```

#### Health Checks (تم)
```
GET /api/health       → شامل
GET /api/health/ready → Kubernetes readiness
GET /api/health/live  → Kubernetes liveness
```

---

### الأسبوع 16-20: Testing Infrastructure

#### اختبارات موجودة:
- `backend/tests/` — E2E tests مع Playwright

#### اختبارات مطلوبة:
```
backend/tests/
  unit/
    test_repositories.py        # tenant isolation
    test_rate_limiting.py       # Redis rate limiting
    test_migrations.py          # migration runner
  integration/
    test_auth_flow.py
    test_tenant_isolation.py    # أهم اختبار
    test_anti_replay.py
  load/
    test_gate_throughput.py     # k6 أو locust
  security/
    test_sql_injection.py
    test_tenant_bypass.py
```

---

## الأولويات حسب الأثر

| الأولوية | الإجراء | الأثر | الجهد |
|---------|---------|------|------|
| 🔴 فوري | `python -m backend.app.migrations.runner --migrate` | indexes + security tables | 5 دقائق |
| 🔴 فوري | `pip install redis rq` + تشغيل worker | background jobs حقيقية | ساعة |
| 🟠 هذا الأسبوع | نقل rate limiting إلى Redis | يعمل مع multiple workers | يوم |
| 🟠 هذا الأسبوع | نقل email/invoice tasks إلى RQ | فصل threading خطير | يوم |
| 🟡 هذا الشهر | نقل `/api/auth/*` إلى blueprint | أول module منفصل | أسبوع |
| 🟡 هذا الشهر | Field encryption للوثائق | حماية بيانات حساسة | أسبوع |
| 🟢 Q3 | تقسيم كامل server.py | maintainability | شهر |
| 🟢 Q3 | PostgreSQL migration | scalability | شهرين |
| 🟢 Q4 | Observability كاملة | monitoring | شهر |

---

## أوامر سريعة

```bash
# تطبيق migrations الآن
python -m backend.app.migrations.runner --migrate

# تشغيل RQ worker
python -m backend.app.tasks.worker

# فحص حالة الـ queues
python -c "from backend.app.tasks import get_queue_stats; import pprint; pprint.pprint(get_queue_stats())"

# تثبيت الـ packages المطلوبة
pip install redis rq

# توليد SECRET_KEY آمن
python -c "import secrets; print(secrets.token_hex(32))"
```
