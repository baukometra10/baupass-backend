# WorkPass — Security Model (ملخص)

## Transport (في الطريق)

| الطبقة | الحالة |
|--------|--------|
| HTTPS / HSTS | ✅ في الإنتاج عبر Railway + middleware |
| Session cookies | ✅ HttpOnly حيث ينطبق؛ Bearer للـ API |
| WebSocket | ✅ نفس origin + auth |

## At-rest (في قاعدة البيانات)

| البيانات | التشفير |
|----------|---------|
| كلمات المرور | ✅ bcrypt (`werkzeug.security`) |
| مفاتيح الأجهزة | ✅ hash فقط |
| Chat messages | **Recommended** — `BAUPASS_FIELD_ENCRYPTION_KEY` with per-tenant `enc:v2:` (Fernet) |
| طلبات الإجازة / PDF | ❌ نص عادي (TLS فقط) |
| لقطات الكameras | base64 في DB — احمِ Volume/backups |

## E2E Chat

**Maximum security mode (default)** — enforced E2E for chat text, attachments, leave notes, contract final text.  
Client: `e2e-crypto.js` (Web), `e2e_crypto_service.dart` (Flutter + Secure Storage).  
Policy env: `BAUPASS_E2E_CHAT_REQUIRED`, `BAUPASS_E2E_ATTACHMENTS_REQUIRED`, `BAUPASS_E2E_SENSITIVE_REQUIRED` (all default `1`).  
Audit: [`docs/SECURITY-AUDIT-E2E.md`](SECURITY-AUDIT-E2E.md) · Roadmap: [`docs/E2E-VERSCHLUESSELUNG.md`](E2E-VERSCHLUESSELUNG.md)

## Bridge / Agent

- RTSP ingest: `BAUPASS_RTSP_BRIDGE_TOKEN` + `secrets.compare_digest`
- Headers مدعومة: `X-WorkPass-Rtsp-Token`, `X-WorkPass-Company-Id` (و aliases Suppix)
- بدون token: 401

## CSRF / CORS

- JSON APIs: Origin check + Bearer bypass
- Forms: CSRF cookie + `X-CSRF-Token`
- CORS whitelist عبر `CORS_ORIGINS`

## Rate limiting

Redis sliding window — scopes: `auth_login`, `worker_api`, `ai_api`, …

## إنتاج — متغيرات حرجة

```
BAUPASS_SECRET_KEY
BAUPASS_AUDIT_SIGNING_KEY
BAUPASS_FIELD_ENCRYPTION_KEY   # موصى به للـ Chat
BAUPASS_RTSP_BRIDGE_TOKEN
PUBLIC_BASE_URL
```

**لا تستخدم:** `BAUPASS_ALLOW_DEMO=1` في الإنتاج.

---

راجع أيضاً: [`docs/enterprise-security/security-architecture-AR.md`](enterprise-security/security-architecture-AR.md)
