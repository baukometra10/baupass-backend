# Multi-Region Readiness (Scaffold)

هذه المرحلة لا تفعّل Multi-Region فعلياً بعد، لكنها تضيف **جاهزية تشغيل** واضحة حتى ننتقل بأمان لاحقاً.

## المتغيرات

```env
BAUPASS_REGION=eu-west
BAUPASS_REGION_STRATEGY=single
BAUPASS_ACTIVE_REGIONS=eu-west,eu-central
```

- `BAUPASS_REGION_STRATEGY=single`: الوضع الحالي (منطقة واحدة).
- `BAUPASS_REGION_STRATEGY=multi`: يتطلب ضبط `BAUPASS_ACTIVE_REGIONS`.

## ماذا تغير

- `/api/health` يعرض ملف السحابة مع:
  - `region`
  - `activeRegions`
  - `regionStrategy`
- `/api/health/ready` صار يشمل فحص `region`.
  - في وضع `multi` يفشل readiness إذا المنطقة الحالية غير موجودة في `BAUPASS_ACTIVE_REGIONS`.

## PostgreSQL Final Cutover Guard

متغير جديد:

```env
BAUPASS_PG_REQUIRED=1
```

عند تفعيله:
- إذا لم يكن `BAUPASS_PG_RUNTIME=1` أو لم يكن PostgreSQL مفعلاً، يرفض التطبيق التشغيل.
- يفيد بعد استقرار النقل النهائي إلى PostgreSQL لمنع العودة غير المقصودة إلى SQLite.

## الترتيب المقترح

1. الآن: `regionStrategy=single`
2. بعد استقرار PG + replica: جهّز region ثانية
3. فعّل `regionStrategy=multi` تدريجياً في staging
4. راقب readiness ثم انقل للإنتاج
