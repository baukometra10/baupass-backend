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
{BASE}/enterprise-hub.html      → 16 طبقة (معاينة)
{BASE}/enterprise               → نفس المركز
```

PowerShell:

```powershell
$BASE = "https://YOUR-APP.up.railway.app"
curl "$BASE/api/health/live"
curl -o NUL -w "%{http_code}" "$BASE/admin-v2/index.html"
```

- [ ] live = OK
- [ ] admin-v2 = 200
- [ ] enterprise-hub يعرض الطبقات

---

## 1b) مركز المؤسسة (~1 دقيقة)

1. `{BASE}/enterprise-hub.html`
2. تحقق من بانر الخطة وعدد القدرات
3. (اختياري) سجّل دخول ثم جرّب مساعد AI على Enterprise

- [ ] تظهر 16 طبقة
- [ ] فلتر «متاح في خطتي» يعمل بعد الدخول

---

## 2) Admin v2 — تعيين البطاقة (~3 دقائق)

1. افتح: `{BASE}/admin-v2/index.html`
2. سجّل دخول **مدير شركة** (أو Superadmin + اختيار الشركة)
3. تبويب **الموظفون**
4. اختر موظفاً للاختبار → أدخل **UID** البطاقة (من القارئ أو تطبيق NFC) → **حفظ**
5. تأكد أن العمود يعرض نفس UID

- [ ] تسجيل الدخول نجح
- [ ] UID محفوظ بدون خطأ `duplicate_physical_card_id`
5. تبويب **Geofence · أتمتة · تكامل** — أضف منطقة geofence تجريبية
6. تبويب **🏛 المؤسسة** — الخريطة الكاملة

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

## 7) Admin v2 — إرسال جماعي + شات (~3 دقائق)

1. `{BASE}/admin-v2/chat.html` → سجّل دخول مدير الشركة
2. **Alle Mitarbeiter benachrichtigen** → رسالة تجريبية
3. (اختياري) استثنِ موظفاً واحداً عبر **Ausnahme**
4. تحقق أن الرسالة تظهر في **قائمة الشات** وداخل محادثة كل موظف
5. على تطبيق Flutter → تبويب **Chat** → نفس الرسالة + إشعار push

- [ ] رسالة النجاح تعرض العدد الصحيح
- [ ] الرسالة ظاهرة عند صاحب العمل
- [ ] الرسالة ظاهرة عند الموظف (بعد APK جديد)

---

## 8) مكالمة صوتية — Admin → موظف (~5 دقائق)

**متطلبات:** APK/iOS جديد بعد آخر push، ويفضل TURN على Railway:

```env
SUPPIX_TURN_URL=turn:global.turn.metered.ca:443?transport=tcp
SUPPIX_TURN_USERNAME=...
SUPPIX_TURN_PASSWORD=...
```

تحقق:

```powershell
python backend/ops/validate_enterprise_env.py --base-url $BASE
```

- [ ] `WebRTC TURN (voice calls)` = configured (أو stun-only للاختبار الأولي)
- [ ] `FCM` = OK (للرنين عبر push)

**الاختبار:**

1. Admin v2 Chat → اختر موظفاً → 📞
2. على هاتف الموظف: **شاشة اتصال كاملة** (حتى خارج تبويب Chat)
3. **Annehmen** → تحدث → كتم / مكبر صوت → **Auflegen**

- [ ] يرن عند الموظف خلال ~2–5 ثوانٍ
- [ ] الصوت واضح في الاتجاهين
- [ ] إنهاء المكالمة من أي طرف يغلق الشاشة

---

## النتيجة

| الحالة | المعنى |
|--------|--------|
| كل ✅ في 1–4 | **MVP جاهز** — التالي: GPS ثم Firebase |
| كل ✅ في 1–4 + 7–8 | **Chat + Sprachanruf جاهز** للميدان |
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
