# المراقبة التشغيلية و SLA

## مؤشرات مقترحة

| KPI | هدف | مصدر |
|-----|-----|------|
| Uptime API | 99.5%+ | `/api/health/ready` |
| p95 API | &lt; 2s | APM |
| فشل login | &lt; 0.5% | audit_logs |
| تأخر webhooks | &lt; 60s | platform_events |
| طابور jobs | &lt; 100 pending | RQ |

## تنبيهات

- 5xx spike
- DB connection errors
- Redis down → fallback mode
- فشل إرسال PDF اليومي

## تقارير حالة

- أسبوعي: ملخص للمشغّل
- شهري: executive PDF (مرتبط بـ reporting roadmap)
