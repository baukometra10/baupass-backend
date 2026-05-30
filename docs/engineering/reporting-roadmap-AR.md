# خارطة طريق التقارير

## موجود

- PDF تشغيل، فواتير، شركات، enterprise، حوادث/زوار
- DATEV CSV بالبريد
- جدولة 08:00 حسب `report_timezone`

## القادم (أولوية)

| تقرير | الجمهور | الحالة |
|-------|---------|--------|
| Executive summary PDF | الإدارة العليا | 📋 |
| Compliance / audit pack | مسؤول امتثال | 📋 |
| تدقيق مجدول (أسبوعي/شهري) | الكل | 📋 |
| توقيع رقمي / أرشفة PDF | حكومي | 📋 |
| تحسين typography PDF | الكل | 🟡 |

## تقني

- منطق التقارير في `backend/app/platform/reports/`
- مسارات HTTP في `domains/reporting/` (منقول)
