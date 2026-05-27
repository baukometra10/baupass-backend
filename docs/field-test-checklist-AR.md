# قائمة تحقق ميدانية (~10 دقائق) — Enterprise Hybrid

استبدل `{BASE}` بعنوان الإنتاج، مثلاً `https://baupass-production.up.railway.app`.

---

## 0) قبل البدء

- [ ] النشر على Railway اكتمل بعد آخر push على `main`
- [ ] هاتف **Android** حقيقي (NFC مفعّل)
- [ ] بطاقة NFC/RFID واحدة + قارئ (اختياري للبديل بدون إنترنت على الهاتف)
- [ ] Flutter مثبت + `flutter doctor` OK

---

## 1) السيرفر حي (~1 دقيقة)

```text
{BASE}/api/health/live          → status: alive
{BASE}/admin-v2/index.html      → HTTP 200
```

PowerShell:

```powershell
$BASE = "https://YOUR-APP.up.railway.app"
curl "$BASE/api/health/live"
curl -o NUL -w "%{http_code}" "$BASE/admin-v2/index.html"
```

- [ ] live = OK
- [ ] admin-v2 = 200

---

## 2) Admin v2 — تعيين البطاقة (~3 دقائق)

1. افتح: `{BASE}/admin-v2/index.html`
2. سجّل دخول **مدير شركة** (أو Superadmin + اختيار الشركة)
3. تبويب **الموظفون**
4. اختر موظفاً للاختبار → أدخل **UID** البطاقة (من القارئ أو تطبيق NFC) → **حفظ**
5. تأكد أن العمود يعرض نفس UID

- [ ] تسجيل الدخول نجح
- [ ] UID محفوظ بدون خطأ `duplicate_physical_card_id`

**بديل:** Legacy `{BASE}/index.html` → تعديل موظف → `physicalCardId`

---

## 3) تطبيق Flutter — بناء وتشغيل (~3 دقائق)

```powershell
cd mobile
flutter create . --org com.baupass --project-name baupass_worker   # مرة واحدة
flutter pub get
```

**هاتف على نفس Wi‑Fi** (استبدل IP الكمبيوتر):

```powershell
flutter run --dart-define=BAUPASS_API_URL=https://YOUR-APP.up.railway.app
```

> للمحاكي استخدم `http://10.0.2.2:8080` مع backend محلي فقط.

- [ ] التطبيق يفتح
- [ ] تسجيل دخول **Badge-ID + PIN** للموظف نفسه

---

## 4) حضور NFC online (~2 دقيقة)

1. تبويب **Attendance** (أو زر NFC من Home)
2. مرّر البطاقة على الهاتف
3. انتظر: `Attendance saved: check-in` (أو check-out)

- [ ] مسح NFC نجح
- [ ] رسالة نجاح من السيرفر
- [ ] في Admin v2 → تبويب **الحضور** أو **نظرة عامة** يظهر السجل

---

## 5) اختياري — offline على الهاتف (~2 دقيقة)

1. فعّل **وضع الطيران** على الهاتف
2. مسح NFC مرة أخرى → رسالة حفظ محلي / pending
3. ألغِ وضع الطيران → اضغط **Sync** في Attendance
4. تحقق من السجل في Admin

- [ ] الطابور يعمل
- [ ] المزامنة بعد عودة الشبكة

---

## 6) اختياري — بطاقة على القارئ (بدون إنترنت هاتف)

1. وضع الطيران على الهاتف
2. مرّر **نفس البطاقة** على قارئ البوابة (متصل بالسحابة)
3. تحقق من الحضور في Admin

- [ ] القارئ سجّل الحدث (البديل الموثوق بدون شبكة هاتف)

---

## النتيجة

| الحالة | المعنى |
|--------|--------|
| كل ✅ في 1–4 | **MVP جاهز** — التالي: GPS ثم Firebase |
| فشل 2 | UID / خطة `nfc_badges` / موظف غير نشط |
| فشل 3–4 | Flutter API URL أو جلسة أو عدم تطابق UID |
| فشل 4 + نجاح 6 | الهاتف غير ضروري للحضور؛ عالجوا القارئ + البطاقة |

---

## روابط سريعة

| | URL |
|--|-----|
| Admin v2 | `{BASE}/admin-v2/index.html` |
| Admin Legacy | `{BASE}/index.html` |
| Worker PWA | `{BASE}/emp-app.html` |
| Health | `{BASE}/api/health/live` |

---

## بعد الاختبار

سجّلوا:

- عنوان `{BASE}` المستخدم
- Badge-ID الموظف (بدون PIN)
- هل `accessMode` = `site_app`؟ (يحتاج GPS لاحقاً)
- رسالة الخطأ إن وُجدت (لقطة شاشة)
