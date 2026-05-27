# تشغيل محلي — دليل سريع (Windows)

## المشكلة الشائعة: Python 3.14

على جهازك **Python 3.14** معطوب (`import json` يفشل). استخدم **Python 3.11** عبر `.venv` (السكربت أدناه يفعل ذلك تلقائياً).

---

## الخطوة 1 — تشغيل Backend

من مجلد المشروع `baustelle`:

```powershell
.\scripts\local-dev-start.ps1
```

أو يدوياً:

```powershell
cd C:\Users\u4363\Desktop\baustelle
.\.venv\Scripts\python.exe backend\server.py
```

المنفذ الافتراضي: **8080** (ليس 5000).

تحقق:

```powershell
curl http://127.0.0.1:8080/api/health/live
```

---

## الخطوة 2 — Admin v2

1. افتح: **http://127.0.0.1:8080/admin-v2/index.html**
2. سجّل دخول **مدير شركة** (نفس مستخدم لوحة Legacy)
3. تبويب **الموظفون** → أدخل UID البطاقة → **حفظ**

لـ Superadmin: اختر نوع الحساب Superadmin ثم اختر **الشركة** من القائمة العلوية.

---

## الخطوة 3 — موظف تجريبي (إن لم يوجد)

من اللوحة الكاملة **http://127.0.0.1:8080/index.html**:

- أضف موظفاً + Badge-ID + PIN
- عيّن `physicalCardId` (أو من Admin v2)

أو استخدم موظفاً موجوداً في قاعدة البيانات المحلية.

---

## الخطوة 4 — تطبيق Flutter (Android)

### تثبيت Flutter

1. https://docs.flutter.dev/get-started/install/windows
2. `flutter doctor` يجب أن يمر Android toolchain

### أول مرة

```powershell
cd mobile
flutter create . --org com.baupass --project-name baupass_worker
flutter pub get
```

### محاكي Android

```powershell
flutter run --dart-define=BAUPASS_API_URL=http://10.0.2.2:8080
```

`10.0.2.2` = localhost من داخل المحاكي.

### هاتف حقيقي (USB)

1. نفس شبكة Wi‑Fi
2. اعرف IP الكمبيوتر: `ipconfig` → مثلاً `192.168.1.50`
3. شغّل:

```powershell
flutter run --dart-define=BAUPASS_API_URL=http://192.168.1.50:8080
```

4. جرّب: Badge-ID + PIN → **Attendance** → مسح NFC

---

## الخطوة 5 — بدون إنترنت (اختبار)

| السيناريو | ماذا تفعل |
|-----------|-----------|
| هاتف بدون شبكة | سجّل حضور NFC → يُحفظ في الطابور → عند Wi‑Fi اضغط Sync |
| لا شبكة على الهاتف أبداً | مرّر **البطاقة على قارئ البوابة** (القارئ متصل بالسحابة) |

---

## روابط سريعة (محلي)

| خدمة | URL |
|------|-----|
| Admin v2 | http://127.0.0.1:8080/admin-v2/index.html |
| Admin Legacy | http://127.0.0.1:8080/index.html |
| Worker PWA | http://127.0.0.1:8080/emp-app.html |
| Health | http://127.0.0.1:8080/api/health/live |

---

## استكشاف الأخطاء

| المشكلة | الحل |
|---------|------|
| `import json` فشل | لا تستخدم Python 3.14؛ شغّل `.\scripts\local-dev-start.ps1` |
| Admin v2 فارغ لـ superadmin | اختر شركة من القائمة |
| Flutter لا يتصل | تأكد من `BAUPASS_API_URL` ومنفذ 8080 |
| NFC لا يعمل | جهاز حقيقي + NFC مفعّل + `physicalCardId` معيّن |
