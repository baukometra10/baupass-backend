# عزل المستأجرين (Tenant Isolation) — BauPass

## النموذج

- **مستأجر = شركة** (`company_id` نصي `cmp-…`)
- كل جداول العمال والمستندات والفواتير مرتبطة بـ `company_id`
- الجلسات (`sessions`) تحمل `company_id` للمستخدم

## آليات الحماية

| آلية | الملف |
|------|--------|
| فلترة استعلامات حسب الشركة | `server.py` · domains · platform |
| Host / tenant | `middleware/tenant.py` |
| Superadmin preview | `preview_company_id` — لا يكتب عبر tenant آخر بدون قصد |
| RBAC enterprise | `platform/rbac/enforcement.py` |

## اختبارات يدوية / CI

1. مستخدم شركة A لا يقرأ `worker_id` لشركة B (IDOR)
2. Superadmin مع `company_id` في query لا يتجاوز preview بدون صلاحية
3. Worker token مربوط بـ `worker.company_id`

## API للتحقق

```http
GET /api/enterprise/layers/security-compliance
GET /api/platform/rbac/catalog
```

## Immutable audit

أحداث التدقيق تحمل `company_id` — سلسلة: `GET /api/enterprise/audit/verify-chain?limit=100`

## إثبات للمشتري

- هذا المستند + نتائج Pentest (بند 3)
- عقد DPA و Data residency (بند 18)
