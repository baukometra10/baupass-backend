# مراحل المنصة — الاستقرار أولاً

## ما يهمك (الأولوية)

1. **استقرار** — لا انقطاع، DB دائم، health/ready يمر، لا demo في الإنتاج  
2. **سرعة** — بوابة الحضور سريعة، Redis للطوابير، SQLite WAL  
3. **أمان كافٍ** — أسرار قوية، rate limit، FCM، عدم تسريب بيانات تجريبية  
4. **تطور المنتج** — فقط بعد أن تبقى النقاط 1–3 خضراء 7 أيام  

---

## المراحل (ما بُني فعلاً)

| المرحلة | المحتوى | الحالة |
|---------|---------|--------|
| **1** | حضور + SQLite + لوحة إدارية | ✅ منجز |
| **2** | Railway + Redis + FCM + enterprise flags | ✅ منجز (تحقق env على Railway) |
| **3** | تشغيل الموقع: ops، inbox، foreman، copilot | ✅ منجز |
| **الآن** | go-live validator + Admin v2 ثلاثي اللغات | ✅ منجز |
| **5** | Postgres cutover | ⏳ جاهز تقنياً — **لا تقطع قبل نسخ احتياطي + اختبار** |
| **6** | متجر التطبيق (APK ثابت → Play/TestFlight) | ⏳ workflow موجود — يحتاج أسرار Firebase + رابط APK |
| **7** | E2E آلي مستمر | 🟡 `e2e_production_smoke.py` + CI يومي |
| **8** | تقليل `server.py` | 📋 تدريجي — **ليس دفعة واحدة** (خطر على الاستقرار) |

---

## الاستقرار — ماذا تفعل أسبوعياً

### يومياً (تلقائي)

- GitHub: `enterprise-go-live` الساعة 06:00 UTC  
- بعد كل نشر Railway: `validate_enterprise_env.py --live-only`  

### يدوياً (5 دقائق)

```powershell
$env:PUBLIC_BASE_URL = "https://baupass-production.up.railway.app"
python backend/ops/e2e_production_smoke.py --base-url $env:PUBLIC_BASE_URL
```

مع JWT (اختياري — inbox/capabilities):

```powershell
$env:BAUPASS_SMOKE_TOKEN = "<token بعد login>"
python backend/ops/e2e_production_smoke.py --base-url $env:PUBLIC_BASE_URL
```

### على Railway (متغيرات حرجة)

| المتغير | لماذا |
|---------|--------|
| `BAUPASS_DB_PATH=/data/baupass.db` | استقرار البيانات |
| `BAUPASS_SECRET_KEY` (طويل عشوائي) | أمان الجلسات |
| `PUBLIC_BASE_URL` | روابط صحيحة |
| `REDIS_URL` + worker RQ | طوابير لا تعلق الويب |
| `FCM_*` | push للتطبيق الهجين |
| **لا** `BAUPASS_ALLOW_DEMO=1` | أمان الإنتاج |

---

## السرعة — ما هو مفعّل

- SQLite: WAL + cache (`sqlite_pragmas.py`)  
- Event bus: Redis/webhooks في خيط خلفي (لا يبطئ البوابة)  
- Rate limiter على Redis في الإنتاج  

**هدف:** `e2e_production_smoke` — health &lt; 3s على instance دافئة.

---

## الأمان — الحد الأدنى المقبول

- [x] Demo معطّل على Railway  
- [x] Enterprise validator بعد النشر  
- [x] Zero-trust / rate limiting (انظر `stability-architecture-AR.md`)  
- [ ] تدوير `BAUPASS_SECRET_KEY` دورياً  
- [ ] `BAUPASS_OPS_SLACK_WEBHOOK_URL` لتنبيهات أمن حرجة  
- [ ] تقييد CORS/عناوين admin إن لزم  

---

## Postgres — متى؟

**فقط عندما:**

1. نسخة SQLite احتياطية حديثة  
2. `postgres_cutover_automation.py` → كل الخطوات خضراء  
3. E2E smoke أخضر 7 أيام متتالية  

```bash
python backend/ops/postgres_cutover_automation.py --sqlite /data/baupass.db
# بعد DATABASE_URL:
python backend/ops/postgres_cutover_automation.py --migrate
# ثم BAUPASS_PG_RUNTIME=1 وإعادة النشر
```

---

## متجر التطبيق — متى؟

1. `mobile-release` GitHub Action → Artifact APK  
2. رفع APK ثابت → `BAUPASS_WORKER_APK_URL`  
3. لاحقاً: Play Internal / TestFlight (أسرار منفصلة)  

---

## تقليل server.py — بأمان

لا حذف دفعة واحدة. الترتيب المقترح:

1. نقل **مجموعة routes** واحدة إلى blueprint موجود (`worker_app`, `platform`)  
2. اختبار smoke + pytest بعد كل نقل  
3. تكرار شهرياً  

الهدف: نفس الـ API، ملفات أصغر، إقلاع أوضح.

---

## Definition of Done — «منصة مستقرة»

- [ ] `e2e_production_smoke` PASS 7 أيام  
- [ ] `setup-status` ≥ 80%  
- [ ] `demoAllowed=false` على `/api/health`  
- [ ] DB `persistent=true`  
- [ ] لا حوادث P1 في inbox/security بدون ack  

عندها فقط: Postgres cutover + متجر + refactor كبير.

---

راجع أيضاً: [`enterprise-go-live-AR.md`](enterprise-go-live-AR.md) · [`stability-architecture-AR.md`](stability-architecture-AR.md) · [`postgres-cutover-steps-AR.md`](postgres-cutover-steps-AR.md)
