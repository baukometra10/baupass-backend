# تسجيل الدخول الموحّد — Microsoft Entra ID (SSO)

## متى تستخدمه

للمشرف العام ومدير الشركة: تسجيل دخول بحساب Microsoft 365 بدل اسم مستخدم/كلمة مرور فقط.

## إعداد Azure

1. **App registration** في Entra ID
2. Redirect URI: `https://YOUR-API/api/auth/entra/callback`
3. Client secret + صلاحية **Microsoft Graph** `User.Read`

## متغيرات Railway / K8s

| المتغير | مثال |
|---------|------|
| `BAUPASS_ENTRA_TENANT_ID` | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `BAUPASS_ENTRA_CLIENT_ID` | Application (client) ID |
| `BAUPASS_ENTRA_CLIENT_SECRET` | Secret value |
| `BAUPASS_ENTRA_REDIRECT_URI` | `https://baupass-production.up.railway.app/api/auth/entra/callback` |
| `BAUPASS_APP_URL` | `https://your-frontend.github.io` أو نطاق WorkPass |

## ربط المستخدم

يجب أن يكون **البريد في جدول users** مطابقاً لبريد Microsoft (`mail` أو `userPrincipalName`). الأدوار المسموحة: `superadmin`, `company-admin`.

## API

- `GET /api/auth/entra/status` — هل SSO مفعّل؟
- `GET /api/auth/entra/start` — بدء تسجيل الدخول
- `GET /api/auth/entra/callback` — عودة من Microsoft (يضبط Cookie الجلسة)

## الواجهة

عند التفعيل يظهر زر **تسجيل الدخول عبر Microsoft** في شاشة الدخول (عربي/ألماني حسب اللغة).

## M365 للتكاملات (ليس SSO)

ربط التقويم/البريد للأتمتة: `POST /api/integrations/microsoft365/connect` — منفصل عن SSO.
