# توزيع تطبيق الموظف (Flutter)

**الاستراتيجية المعتمدة:** توزيع **داخلي أولاً** (APK على Android، TestFlight على iPhone)، ثم المتاجر العامة لاحقاً عند الاستقرار. راجع [enterprise-hybrid-mobile-architecture.md](./enterprise-hybrid-mobile-architecture.md).

## لماذا لا يُحدَّث التطبيق تلقائياً مثل الموقع؟

| ما يُنشر على Railway | ما يحتاج خطوة إضافية |
|----------------------|----------------------|
| Backend API | تطبيق Flutter (APK / IPA) |
| Admin v2 (صفحة ويب) | تثبيت يدوي أو متجر تطبيقات |

الويب يصل للمستخدم فور النشر. التطبيق الأصلي يجب **بناؤه** ثم **تثبيته** على كل هاتف (أو نشره عبر Google Play / App Store بحسابك).

## ماذا يمكن للمشروع فعله الآن؟

1. **CI على GitHub** — بعد دفع `main`، workflow `Build worker APK` يبني `app-release.apk`.
   - افتح: **Actions** → **Build worker APK** → آخر تشغيل → **Artifacts** → `baupass-worker-apk`.
2. **تشغيل يدوي** — Actions → **Run workflow** → غيّر `api_base_url` إن لزم.
3. **محلياً** (بعد تثبيت Flutter + Android SDK):
   ```powershell
   cd mobile
   flutter create . --org com.baupass --project-name baupass_worker
   flutter pub get
   flutter build apk --release --dart-define=BAUPASS_API_URL=https://baupass-production.up.railway.app
   ```
   الملف: `mobile\build\app\outputs\flutter-apk\app-release.apk`

## تفعيل موظف (QR — Admin v2)

1. **Admin v2** → تبويب **الموظفون** → **QR تفعيل**
2. الموظف يمسح الرمز → `join.html` → تثبيت (APK أو TestFlight) → **فتح في التطبيق**
3. على Railway عيّن: `BAUPASS_WORKER_APK_URL`, `BAUPASS_TESTFLIGHT_URL`

تفاصيل: [testflight-internal-distribution.md](./testflight-internal-distribution.md)

## TestFlight (iPhone — المرحلة 1)

1. حساب Apple Developer (99$/سنة).
2. `flutter build ipa` + رفع عبر Xcode / Transporter إلى App Store Connect.
3. إضافة موظفين كمختبرين داخل TestFlight (حتى آلاف المستخدمين حسب البرنامج).
4. تحديثات أسرع من المراجعة العامة؛ مناسب لاختبار Core NFC.

## ما لا يمكن أتمتته بدونك

- **Google Play / App Store (المرحلة 2)** — عند الجاهزية للإنتاج العام.
- **توزيع تلقائي لكل الموظفين** — في المرحلة 1: رابط APK، QR، أو MDM؛ على iOS: دعوة TestFlight.

APK من CI موقّع بمفتاح **debug** (مناسب للاختبار الميداني). للإنتاج العام استخدم keystore خاص بك وعدّل `signingConfig` في `mobile/android/app/build.gradle.kts`.

## اختبار سريع بعد التثبيت

1. Admin v2: ربط `physical_card_id` = UID البطاقة.
2. تسجيل دخول Badge + PIN في التطبيق.
3. مسح NFC → تحقق من `access_logs` في Admin.

راجع أيضاً: `docs/field-test-checklist-AR.md`.
