# خارطة طريق SSO المؤسسي

## الحالة الحالية

| البروتوكول / المزود | الحالة | ملاحظات |
|---------------------|--------|---------|
| OpenID Connect | ✅ جزئي | Entra + Google |
| Microsoft Entra ID | ✅ | `docs/sso-entra-AR.md` |
| Google Workspace | ✅ | `docs/sso-google-AR.md` |
| SAML 2.0 | 📋 مخطَّط | IdP-initiated + SP metadata |
| Keycloak / Generic OIDC | 🟡 | `BAUPASS_KEYCLOAK_ISSUER`, `BAUPASS_KEYCLOAK_CLIENT_ID`, … — `/api/auth/keycloak/*` |
| SAML 2.0 | 🟡 scaffold | `BAUPASS_SAML_*` — metadata + ACS placeholder |
| Active Directory | 🟡 | عبر Entra Connect أو Keycloak LDAP |
| كتالوج موحّد | ✅ | `GET /api/auth/sso/catalog` |

## متطلبات مؤسسية شائعة

- **JIT provisioning** — إنشاء مستخدم عند أول دخول SSO إن كان البريد معروفاً.
- **Group → Role mapping** — ربط مجموعات Entra بأدوار BauPass (بعد تفعيل الأدوار المؤسسية).
- **SCIM** (اختياري لاحقاً) — مزامنة المستخدمين من HR.

## API للكتالوج

`GET /api/platform/rbac/catalog` يعرض حالة SSO:

```json
"sso": { "oidc": "active", "saml": "planned", "keycloak": "planned", "ad_ldap": "planned" }
```

## ترتيب التنفيذ المقترح

1. SAML 2.0 عام (python3-saml أو authlib).
2. Keycloak كـ IdP مرجعي للاختبار.
3. Group mapping + أدوار `department_admin`, `auditor`, …
4. SCIM (مرحلة لاحقة).

## قيود تشغيلية اليوم

- حالة OIDC **في الذاكرة** (instance واحد) — للتوسع: Redis لـ state/PKCE.
- المستخدم يجب أن يكون `users.email` مطابقاً لـ IdP.
