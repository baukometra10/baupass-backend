# BauPass — خطط الاشتراك والـ 16 طبقة

## الخطط الأربع

| الخطة | السعر (EUR) | الجمهور |
|-------|-------------|---------|
| **Tageskarte** | 19/يوم | موقع زائر / يوم واحد |
| **Starter** | 149/شهر | شركة صغيرة + تطبيق موظف + NFC |
| **Professional** | 999/شهر | تشغيل لحظي + أتمتة + فوترة + عمليات |
| **Enterprise** | 2490/شهر | AI + تكاملات SAP/Oracle + قيادة عالمية |

## أين ترى كل شيء

**`/enterprise-hub.html`** — كل قدرة من قائمة الرؤية مع:
- طبقة (1–16)
- سطح العرض (Legacy / Admin v2 / Worker / Hub / API)
- **هل مفعّل لخطتك** أو يحتاج ترقية
- روابط الواجهة و API

## APIs

```http
GET /api/platform/enterprise-catalog
GET /api/platform/entitlements
```

## تخصيص حسب الخطة

- كل قدرة لها `minPlan` في `backend/app/platform/plan_entitlements.py`
- الـ API يحترم الخطة (`403 feature_not_available`) — مثال: AI على Enterprise
- تغيير خطة الشركة: Legacy → إعدادات الشركة → حقل Plan

## تغطية تقريبية

| الخطة | نسبة القدرات في الكتالوج |
|-------|---------------------------|
| Tageskarte | ~25% |
| Starter | ~55% |
| Professional | ~75% |
| Enterprise | 100% |

> بعض القدرات «config» (Wallet، Redis، K8s) تحتاج إعداد بنية تحتية بجانب الخطة.
