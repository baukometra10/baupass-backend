# برنامج اعتماد الأجهزة (Hardware Certification)

## نطاق

- بوابات Turnstile / RFID
- أجهزة tablet للإدارة
- جسر RTSP للكاميرات (`device-signature-bridge-DE.md`)

## مستويات

| مستوى | معنى |
|-------|------|
| Compatible | يعمل في مختبر WorkPass |
| Certified | اختبار ميداني + دعم رسمي |
| Deprecated | لا يُباع للعملاء الجدد |

## عملية

1. مواصفات من المصنع
2. اختبار API (`/api/integrations/*`)
3. توثيق firmware / TLS
4. إدراج في `enterprise_catalog` integrations
