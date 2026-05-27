# نشر Multi-Region (دليل تشغيل)

الكود يدعم:
- `BAUPASS_REGION` / `BAUPASS_ACTIVE_REGIONS` / `BAUPASS_REGION_STRATEGY`
- جدول `company_data_residency` (migration **017**)
- `BAUPASS_ENFORCE_DATA_RESIDENCY=1` لمنع الكتابة من منطقة خاطئة

## خطوات Railway (مثال EU + US)

1. خدمتان API: `eu-west` و `us-east` مع نفس `DATABASE_URL` (أو replica per region لاحقاً)
2. على كل خدمة:
   ```env
   BAUPASS_REGION=eu-west
   BAUPASS_REGION_STRATEGY=multi
   BAUPASS_ACTIVE_REGIONS=eu-west,us-east
   ```
3. DNS / Load balancer يوجّه حسب Geo (Cloudflare) — خارج هذا المستودع
4. لكل شركة:
   ```http
   PUT /api/platform/companies/{id}/data-residency
   {"data_region":"eu-west","policy":"strict"}
   ```

## التحقق

```http
GET /api/platform/global-readiness
GET /api/health/ready
```
