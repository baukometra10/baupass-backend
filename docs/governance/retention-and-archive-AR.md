# الاحتفاظ والأرشفة

## سياسات مقترحة (قابلة للتخصيص لكل مستأجر)

| البيانات | افتراضي | Legal hold |
|----------|---------|------------|
| سجلات دخول | 7 سنوات | يوقف الحذف |
| مستندات امتثال | مدة العقد + 90 يوم | نعم |
| فواتير | 10 سنوات | نعم |
| audit_logs | 3–7 سنوات | نعم |

## ميزات مستهدفة

- `retention_policy` per company
- **Immutable archive** (append-only bucket + hash chain)
- **Legal hold** flag على worker/company
- **Full export** (JSON + PDF pack) للجهات الرقابية

## حالة التنفيذ

📋 تصميم schema — التنفيذ في المرحلة B من `enterprise-roadmap-2026-AR.md`
