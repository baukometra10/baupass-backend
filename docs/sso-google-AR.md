# تسجيل الدخول — Google Workspace (SSO)

## الإعداد في Google Cloud Console

1. مشروع OAuth 2.0 → **Credentials** → OAuth client (Web)
2. Redirect URI: `https://YOUR-API/api/auth/google/callback`
3. Scopes: `openid email profile`

## المتغيرات

| المتغير | الوصف |
|---------|--------|
| `BAUPASS_GOOGLE_CLIENT_ID` | Client ID |
| `BAUPASS_GOOGLE_CLIENT_SECRET` | Client secret |
| `BAUPASS_GOOGLE_REDIRECT_URI` | Callback URL الكامل |
| `BAUPASS_APP_URL` | واجهة WorkPass (لإعادة التوجيه بعد الدخول) |

## ربط المستخدم

البريد في `users.email` يجب أن يطابق حساب Google. الأدوار: `superadmin`, `company-admin`.

## API

- `GET /api/auth/google/status`
- `GET /api/auth/google/start`
- `GET /api/auth/google/callback`

زر **تسجيل الدخول عبر Google** يظهر في شاشة الدخول عند التفعيل.
