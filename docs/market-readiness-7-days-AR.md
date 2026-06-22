# WorkPass — خطة 7 أيام للسوق (PWA فقط)

> **الهدف:** جاهزية بيع وعرض — ليس بناء كل قائمة enterprise.  
> **لا native apps** — Worker PWA + Admin PWA كما هو اليوم.

---

## اليوم 1 — استقرار البيانات (الأهم)

### Railway (إلزامي)

1. Volume على **`/data`**
2. `BAUPASS_DB_PATH=/data/baupass.db`
3. `BAUPASS_BACKUP_ON_BOOT=1`
4. `PUBLIC_BASE_URL=https://YOUR-DOMAIN.up.railway.app`

### اختبار

| # | الخطوة | النتيجة المتوقعة |
|---|--------|------------------|
| 1 | `GET /api/health` | `persistent: true` |
| 2 | إنشاء عامل تجريبي في Admin | يظهر في القائمة |
| 3 | Redeploy من GitHub | **نفس** العامل ما زال موجوداً |
| 4 | `GET /api/admin/database/backups` (superadmin) | نسخة احتياطية موجودة |

### رسالة للعميل

«بياناتكم على قرص دائم — لا تختفي بعد التحديث».

---

## اليوم 2 — Redis + مهام الخلفية

### Railway

1. **New** → **Database** → **Redis**
2. ربط `REDIS_URL` بالخدمة الرئيسية (Reference Variable)
3. متغيرات:

```env
REDIS_URL=${{Redis.REDIS_URL}}
BAUPASS_DAILY_JOBS_MODE=rq
BAUPASS_INVOICE_RETRY_MODE=rq
BAUPASS_DUNNING_MODE=rq
BAUPASS_WORKER_SESSION_CLEANUP_MODE=rq
```

4. خدمة ثانية (اختياري لكن موصى به):

| الإعداد | القيمة |
|---------|--------|
| Start | `python -m backend.app.tasks.worker` |
| نفس `REDIS_URL` | نعم |

### اختبار

| # | الخطوة | النتيجة |
|---|--------|---------|
| 1 | `GET /api/health` | `redis: ok`, `queues: ok` |
| 2 | `GET /api/health/queues` | إحصائيات queues |
| 3 | إرسال فاتورة تجريبية | لا timeout طويل على الواجهة |

راجع: [railway-production-setup-AR.md](./railway-production-setup-AR.md)

---

## اليوم 3 — سيناريو العامل على الموقع (PWA)

### سيناريو Standort-App (صناعة)

| # | خطوة | تحقق |
|---|------|------|
| 1 | شركة: `access_mode = site-app` + نصف قطر 15–25م | Admin محفوظ |
| 2 | عامل: فتح PWA من QR سريع | Badge + PIN أو دخول مباشر |
| 3 | داخل الموقع | تسجيل دخول تلقائي (إن مفعّل) |
| 4 | مغادرة الموقع | خروج تلقائي |
| 5 | طلب إجازة أونلاين | لا «session not found» |

### سيناريو بوابة (بناء كلاسيكي)

| # | خطوة | تحقق |
|---|------|------|
| 1 | Tap NFC/QR على البوابة | check-in |
| 2 | Admin: `/api/operations/snapshot` | `workersOnSite` يزيد |
| 3 | check-out | ينقص |

---

## اليوم 4 — الامتثال والمستندات (بيع B2B)

| # | اختبار | تحقق |
|---|--------|------|
| 1 | رفع مستند بتاريخ انتهاء قريب | يظهر تنبيه |
| 2 | `GET /api/operations/snapshot` | `expiringDocs7Days` |
| 3 | عامل بدون توقيع امتثال | يظهر في KPI |
| 4 | `GET /api/compliance/expiry-predictions` (بعد migrate) | قائمة مخاطر |

### رسالة للعميل

«تنبيه قبل انتهاء التصاريح — لا مفاجآت على البوابة».

---

## اليوم 5 — الأمان والثقة

| # | اختبار | تحقق |
|---|--------|------|
| 1 | تفعيل 2FA لـ superadmin | OTP يعمل |
| 2 | محاولة login خاطئة 6 مرات | rate limit |
| 3 | `GET /api/audit-trail` | أحداث login/logout |
| 4 | HTTPS + PWA install | أيقونات بدون `?v=` |

اختياري:

```env
BAUPASS_REQUIRE_SUPERADMIN_2FA=1
SENTRY_DSN=https://...
```

---

## اليوم 6 — لوحة حية + API للشركاء

| # | endpoint | الغرض |
|---|----------|--------|
| 1 | `GET /api/operations/snapshot` | KPI اليوم |
| 2 | `GET /api/dashboard/live` | أحداث + حضور |
| 3 | `GET /api/v2/workforce/tracking` | تتبع مباشر |
| 4 | `POST /api/developer/api-keys` | مفتاح تكامل |
| 5 | `GET /api/v1/workers` + `X-Api-Key` | API شريك |

### اختبار WebSocket/SSE (اختياري)

- `GET /api/v1/stream/events` (SSE) من Admin مسجّل
- SocketIO: اتصال من المتصفح مع `subscribe` + `company_id`

---

## اليوم 7 — عرض تجاري + مراجعة نهائية

### Demo script (15 دقيقة)

1. Admin: شركة + أوقات عمل + Standort-App  
2. عامل: QR → دخول فوري → شاشة بسيطة  
3. خريطة/موقع: دخول وخروج تلقائي  
4. Admin: لوحة — من على الموقع الآن  
5. مستند ينتهي → تنبيه  
6. فاتورة شهرية + dunning (عرض فقط)  
7. White-label: شعار الشركة  

### Checklist نهائي قبل العرض لعميل كبير

- [ ] `/api/health` → `persistent: true`
- [ ] Redis متصل
- [ ] لا أخطاء Sentry حرجة (إن مُفعّل)
- [ ] PWA يعمل offline (وضع طائرة — فتح الكاش)
- [ ] بريد SMTP اختبار ناجح
- [ ] نسخة احتياطية DB موجودة

---

## ما نؤجّله (بعد أول عميل مدفوع كبير)

- PostgreSQL كامل (انظر cutover عند الحاجة)
- تكامل SAP / M365 كامل
- Multi-region
- AI متقدم (بدون `OPENAI_API_KEY` اختياري)

---

## مراجع

- [github-railway.md](./github-railway.md)
- [railway-production-setup-AR.md](./railway-production-setup-AR.md)
- [ENTERPRISE-CHECKLIST-AR.md](./ENTERPRISE-CHECKLIST-AR.md)
