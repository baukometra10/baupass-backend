# بوابة نجاح العملاء (Customer Success Portal)

## الغرض

للعملاء Enterprise: متابعة العقد، التدريب، التذاكر، حالة الخدمة، وإصدارات المنصة.

## مكونات مقترحة (مرحلة D)

| وحدة | وصف |
|------|-----|
| Dashboard | SLA uptime، حوادث مفتوحة، آخر نشر |
| Contracts | خطة، seats، تاريخ تجديد |
| Training | روابط فيديو / جلسات onboarding |
| Support | تذاكر (Zendesk / Freshdesk تكامل) |
| Documents | مسار ISO، pentest summary، DPA |

## تقني

- SSO نفس Entra للعميل
- قراءة فقط من `GET /api/health/*` و webhooks status
- لا بيانات عمال عبر البوابة — فقط metadata تشغيلية

## أولوية

بعد المرحلة B (امتثال) — لا يعطل تفكيك `server.py`.
