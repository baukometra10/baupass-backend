# Smoke Token + APK — خطوتان للاستقرار

## 1) `BAUPASS_SMOKE_TOKEN` (GitHub)

يفحص CI صندوق الوارد والقدرات بعد تسجيل الدخول.

### محلياً

```powershell
cd c:\Users\u4363\Desktop\baustelle
$env:PUBLIC_BASE_URL = "https://baupass-production.up.railway.app"
.\scripts\get-smoke-token.ps1
# أو بدون حوار:
$env:BAUPASS_SMOKE_USER = "superadmin"
$env:BAUPASS_SMOKE_PASSWORD = "***"
.\scripts\get-smoke-token.ps1
```

### في GitHub

1. **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret**
   - Name: `BAUPASS_SMOKE_TOKEN`
   - Value: JWT من السكربت أعلاه
3. تأكد أن `PUBLIC_BASE_URL` موجود أيضاً

### تحقق

```powershell
$env:BAUPASS_SMOKE_TOKEN = "<jwt>"
python backend/ops/e2e_production_smoke.py --base-url https://baupass-production.up.railway.app
```

يجب أن يمر `capabilities_auth` و `inbox_counts_auth` (وليس `auth_skipped` فقط).

**ملاحظة:** عند انتهاء الجلسة، أعد توليد التوكن وحدّث السر (شهرياً أو عند فشل CI).

---

## 2) `mobile-release` → `BAUPASS_WORKER_APK_URL`

### تشغيل البناء

1. GitHub → **Actions** → **mobile-release** → **Run workflow**
2. `api_base_url`: `https://baupass-production.up.railway.app`
3. انتظر Job أخضر → Artifact **`baupass-worker-release`** → حمّل `app-release.apk`

اختياري: Secret **`FIREBASE_GOOGLE_SERVICES_JSON`** (محتوى ملف google-services.json) لتفعيل FCM في APK.

### استضافة APK (HTTPS عام)

اختر واحداً:

| الطريقة | مثال |
|---------|------|
| GitHub Release | `https://github.com/baukometra10/baupass-backend/releases/download/v1.0.0/app-release.apk` |
| CDN / Storage | رابط ثابت HTTPS |
| Railway static | إن رُفع على خدمة ملفات |

### Railway

```env
BAUPASS_WORKER_APK_URL=https://YOUR-PUBLIC-URL/app-release.apk
```

ثم أعد النشر وتحقق:

- `GET /worker-build.json` → يحتوي `apkUrl`
- `join.html` → زر تحميل التطبيق

---

## 3) بعد الإعداد

- `enterprise-go-live` (يومي) + `railway-deploy` يشغّلان `e2e_production_smoke`
- راجع [`platform-phases-stability-AR.md`](platform-phases-stability-AR.md)
