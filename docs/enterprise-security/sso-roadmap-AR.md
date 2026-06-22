# خارطة طريق SSO المؤسسي

## الحالة الحالية

| البروتوكول / المزود | الحالة | ملاحظات |
|---------------------|--------|---------|
| OpenID Connect | ✅ جزئي | Entra + Google |
| Microsoft Entra ID | ✅ | `docs/sso-entra-AR.md` |
| Google Workspace | ✅ | `docs/sso-google-AR.md` |
| Keycloak / Generic OIDC | 🟡 | `BAUPASS_KEYCLOAK_ISSUER`, `BAUPASS_KEYCLOAK_CLIENT_ID`, … — `/api/auth/keycloak/*` |
| SAML 2.0 | 🟡 **native** | `BAUPASS_SAML_*` — `/api/auth/saml/start` redirect + `/api/auth/saml/acs` + metadata XML |
| Active Directory | 🟡 | عبر Entra Connect أو Keycloak LDAP |
| كتالوج موحّد | ✅ | `GET /api/auth/sso/catalog` |

## متطلبات مؤسسية شائعة

- **JIT provisioning** — إنشاء مستخدم عند أول دخول SSO إن كان البريد معروفاً.
- **Group → Role mapping** — ربط مجموعات Entra بأدوار WorkPass (بعد تفعيل الأدوار المؤسسية).
- **SCIM** (اختياري لاحقاً) — مزامنة المستخدمين من HR.

## API للكتالوج

`GET /api/platform/rbac/catalog` يعرض حالة SSO:

```json
"sso": { "oidc": "active", "saml": "planned", "keycloak": "planned", "ad_ldap": "planned" }
```

## متغيرات SAML

| متغير | مطلوب |
|--------|--------|
| `BAUPASS_SAML_ENTITY_ID` | ✅ SP entity ID |
| `BAUPASS_SAML_ACS_URL` | ✅ e.g. `https://host/api/auth/saml/acs` |
| `BAUPASS_SAML_IDP_SSO_URL` | ✅ IdP SSO URL |
| `BAUPASS_SAML_IDP_CERT_PEM` | ✅ شهادة IdP (PEM) |
| `BAUPASS_SAML_ALLOW_UNSIGNED` | اختبار فقط — `1` يسمح بدون توقيع XML |
| `BAUPASS_SAML_SKIP_SIGNATURE_VERIFY` | dev فقط |

Metadata: `GET /api/auth/saml/metadata` (XML) أو `/metadata.json`

## ترتيب التنفيذ المقترح

1. ~~SAML redirect + ACS~~ ✅ (`saml_flow.py`)
2. Keycloak كـ IdP مرجعي للاختبار.
3. Group mapping + أدوار `department_admin`, `auditor`, …
4. SCIM (مرحلة لاحقة).

## حالة SSO (Redis)

| متغير | الوصف |
|--------|--------|
| `REDIS_URL` | عند التعيين يُخزَّن state في Redis تلقائياً (مناسب لـ Railway متعدد النسخ) |
| `BAUPASS_SSO_STATE_REDIS=1` | إجبار Redis حتى مع `REDIS_URL` |
| `BAUPASS_SSO_STATE_REDIS=0` | تعطيل Redis — ذاكرة العملية فقط |
| `BAUPASS_SSO_STATE_TTL_SEC` | افتراضي `600` |

التنفيذ: `backend/app/platform/auth/sso_state.py` — Entra، Google، Keycloak، SAML.

## قيود تشغيلية اليوم

- التحقق الكامل من توقيع XML-DSig لـ SAML ما زال اختيارياً (`BAUPASS_SAML_SKIP_SIGNATURE_VERIFY`).
- المستخدم يجب أن يكون `users.email` مطابقاً لـ IdP.
