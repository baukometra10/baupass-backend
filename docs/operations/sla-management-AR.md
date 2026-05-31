# إدارة اتفاقيات مستوى الخدمة (SLA Management)

## مراقبة تقنية (موجود)

- `docs/operations/sla-monitoring-AR.md`
- Grafana dashboards: `deploy/grafana/`
- `GET /api/health/ready` · `GET /api/health/dr`

## SLA مقترحة للعقود Enterprise

| مؤشر | هدف | قياس |
|------|-----|------|
| توفر API | 99.5% / شهر | uptime monitor |
| زمن استجابة P95 | < 800ms | APM / logs |
| RTO | 4h | DR runbook |
| RPO | 24h | backup يومي |
| دعم P1 | 4h استجابة | تذكرة + on-call |

## Inbox SLA داخل المنتج

عمليات Posteingang: `slaHours` / `slaStatus` في `platform/inbox/service.py`.

## بوابة العميل (مستقبل — بند 19)

عرض حالة الخدمة، حوادث مفتوحة، واتفاقية العقد في Customer Success Portal.
