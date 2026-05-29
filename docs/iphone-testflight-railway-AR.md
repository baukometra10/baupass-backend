# تطبيق الموظف على iPhone + مفاتيح الخادم (Railway)

**المرجع السريع للمتغيرات:** [`.env.worker-mobile.example`](../.env.worker-mobile.example)  
**فحص بعد النشر:** `GET /api/worker-app/mobile-setup` (بدون أسرار — يعرض ما نُقص)

---

## 1) ماذا تضع على Railway (الخادم)

### إلزامي — بدونها لا يعمل النظام

| المتغير | مثال | الغرض |
|---------|------|--------|
| `PUBLIC_BASE_URL` | `https://baupass-production.up.railway.app` | QR، `join.html`، deep link |
| `BAUPASS_SECRET_KEY` | 64+ حرف عشوائي | أمان الجلسات |
| `BAUPASS_AUDIT_SIGNING_KEY` | 64+ حرف عشوائي | توقيع السجلات |
| `BAUPASS_DB_PATH` | `/data/baupass.db` | SQLite + Volume `/data` |
| `BAUPASS_PG_RUNTIME` | `0` | SQLite (أو `1` + `DATABASE_URL` لـ Postgres) |
| `BAUPASS_WORKER_JWT_SECRET` | 32+ حرف عشوائي | JWT تطبيق الموظف |
| `BAUPASS_WORKER_DEVICE_BINDING` | `1` | ربط الهاتف بالحساب |
| `BAUPASS_WORKER_JWT` | `1` | JWT في الاستجابة |

### إلزامي لـ iPhone (TestFlight)

| المتغير | مثال |
|---------|------|
| `BAUPASS_TESTFLIGHT_URL` | `https://testflight.apple.com/join/XXXXXXXX` |

### موصى به

| المتغير | الغرض |
|---------|--------|
| `REDIS_URL` | مهام الخلفية |
| `BAUPASS_WORKER_SESSION_CLEANUP_MODE` | `rq` + خدمة worker |
| `BAUPASS_WORKER_APK_URL` | Android (ليس iPhone) |
| `FCM_PROJECT_ID` + `FCM_SERVICE_ACCOUNT_JSON` | Push (اختياري للبداية) |

### لا تحتاجه في البداية

- `BAUPASS_PLAY_STORE_URL` / `BAUPASS_APP_STORE_URL`
- Apple Wallet / Google Wallet
- `VAPID_*` (PWA قديم فقط)

---

## 2) قالب جاهز للنسخ

انسخ من [`.env.worker-mobile.example`](../.env.worker-mobile.example) إلى Railway → **Variables** → **Redeploy**.

---

## 3) التحقق من الخادم

```powershell
$BASE = "https://baupass-production.up.railway.app"
Invoke-RestMethod "$BASE/api/worker-app/mobile-setup" | ConvertTo-Json -Depth 6
Invoke-RestMethod "$BASE/worker-join-config.json"
```

توقّع في `mobile-setup`:

- `readiness.coreBackend`: `true`
- `readiness.iphoneTestFlight`: `true` (بعد ضبط TestFlight)
- `missingRequired`: `[]`

---

## 4) بناء التطبيق على iPhone (ليس على Railway)

| أين | القيمة |
|-----|--------|
| **عند `flutter build ipa`** | `--dart-define=BAUPASS_API_URL=<نفس PUBLIC_BASE_URL>` |
| **Apple** | Bundle `com.baupass.worker`، NFC Tag Reading |
| **TestFlight** | رفع IPA → رابط الدعوة → `BAUPASS_TESTFLIGHT_URL` |

```bash
cd mobile
flutter pub get
flutter build ipa --release \
  --dart-define=BAUPASS_API_URL=https://baupass-production.up.railway.app
```

رفع عبر Transporter أو Xcode → App Store Connect → TestFlight.

CI (unsigned): GitHub Actions **Build worker iOS** → artifact للتوقيع المحلي.

---

## 5) تفعيل موظف

1. Admin v2 → الموظفون → **QR تفعيل**
2. iPhone: `join.html` → **TestFlight** → تثبيت
3. مسح QR مرة أخرى → **In BauPass-App öffnen** (`baupass://join?access=...`)
4. أو Badge-ID + PIN
5. Admin: `physical_card_id` = UID البطاقة
6. التطبيق → Attendance → NFC

---

## 6) APIs المستخدمة (بدون إعادة بناء Backend)

| الوظيفة | المسار |
|---------|--------|
| دخول | `POST /api/worker-app/login` |
| ملف | `GET /api/worker-app/me` |
| QR ديناميكي | `GET /api/worker-app/dynamic-qr` |
| حضور NFC | `POST /api/worker-app/attendance/nfc` |
| Offline | `POST /api/worker-app/offline-events` |
| Geofence | `POST /api/worker-app/site-presence` |
| Push | `POST /api/worker-app/push/register` |

---

## مراجع

- [testflight-internal-distribution.md](./testflight-internal-distribution.md)
- [distribute-worker-app-AR.md](./distribute-worker-app-AR.md)
- [enterprise-hybrid-platform-AR.md](./enterprise-hybrid-platform-AR.md)
- [mobile/README.md](../mobile/README.md)
