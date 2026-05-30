# تشغيل معزول (Air-Gapped) — المرحلة C

## المتطلبات

- Kubernetes داخلي أو VM بدون إنترنت صادر
- PostgreSQL و Redis داخل الشبكة
- صور Docker مُحمَّلة مسبقاً (`docker load`)
- `BAUPASS_AIR_GAPPED=1`
- `BAUPASS_AUDIT_SIGNING_KEY` قوي (32+ حرف)

## Helm

```bash
helm upgrade --install baupass ./deploy/helm/baupass \
  -f deploy/helm/baupass/values.yaml \
  -f deploy/helm/baupass/values-government.yaml \
  --set existingSecret=baupass-secrets
```

## SSO في البيئة المعزولة

- **Keycloak** محلي: `BAUPASS_KEYCLOAK_ISSUER=https://idp.internal/realms/baupass`
- **SAML** مع IdP حكومي داخلي (بعد تفعيل ACS الكامل)
- تعطيل Entra/Google إن لم يكن هناك خروج للإنترنت

## SIEM داخلي

```http
GET /api/enterprise/security/siem-export?format=cef&source=both&limit=500
Authorization: Bearer …
```

وجّه المخرجات إلى مجمّع Syslog/Splunk عبر sidecar أو CronJob.

## تحقق سلسلة التدقيق

```http
GET /api/enterprise/security/audit-chain/verify
```

## قيود

- لا تحديثات تلقائية للحزم — مسار patch يدوي
- Push notifications قد تتطلب FCM — عطّل أو استخدم بوابة داخلية
