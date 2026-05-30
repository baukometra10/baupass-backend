# رؤية منصة BauPass — منصة تشغيل وامتثال للمؤسسات والحكومة

## 1. الهدف الاستراتيجي

بناء **منصة تشغيل موحّدة** لا تُدار يدوياً فقط، بل:

- **تراقب** البيانات الحية (دخول/خروج، مستندات، فواتير، أمان).
- **تقرّر** متى يُنفَّذ إجراء (قواعد أتمتة + ذكاء اصطناعي + إرشادات).
- **تُبلّغ** المسؤول في الوقت المناسب (بريد PDF، إشعار، Push، مركز قيادة).

المنصة جاهزة للتأجير لشركات البناء **والوزارات / الجهات الحكومية** مع عزل المستأجرين (Multi-Tenant) وخيار **سحابة خاصة**.

---

## 2. ما هو موجود اليوم (جاهز أو شبه جاهز)

| القدرة | الحالة |
|--------|--------|
| تعدد المستأجرين (شركة = Mandant) | ✅ |
| White-Label (اسم، لون، شعار) | ✅ |
| بوابة المشرف + تطبيق العامل + Turnstile | ✅ |
| مستندات + Lohn-PDF + OCR في البريد | ✅ |
| DATEV CSV + OAuth DATEV | ✅ (يتطلب مفاتيح Env) |
| 6 طبقات Enterprise + Physical Operations | ✅ |
| محرك أتمتة (Automation Rules) | ✅ |
| BauPass KI (صوت، نوايا، إجراءات) | ✅ |
| إشعارات العامل (Push + مركز إشعارات) | ✅ |
| توقيع الامتثال على الكرت (Compliance Signature) | ✅ في لوحة الإدارة |
| كاميرا / أحداث أمن (Webhook API) | ✅ `security-cameras/events` |
| قارئ بصمة / HCE / NFC | ✅ |
| PostgreSQL + Docker + Railway | ✅ |
| تقرير PDF بالبريد + إرشادات تشغيل | ✅ `/api/reporting/email-pdf`, `/api/ops/guidance`, DATEV-CSV مرفق |
| جدولة 08:00 حسب المنطقة | ✅ `BAUPASS_TIMEZONE` / `companies.report_timezone`, فحص كل 15 دقيقة |
| DATEV-CSV بالبريد | ✅ `/api/reporting/email-datev-csv` + زر في لوحة Reporting |

---

## 3. القرارات والإرشادات في الوقت المناسب

### 3.1 ثلاث طبقات

1. **قواعد فورية (Automation)** — عند حدث (مثلاً فاتورة متأخرة): قفل، تنبيه، إرسال PDF.
2. **إرشادات (Guidance)** — `/api/ops/guidance`: توصيات بالعربية/الألمانية (فواتير، أمان، طوارئ، Check-out).
3. **ذكاء اصطناعي (Copilot)** — سؤال/جواب + تلخيص يومي + إجراءات (بريد، Slack، Push).

### 3.2 التطوير القادم (أولوية عالية)

- جدولة يومية: **08:00** تقرير PDF تلقائي لكل `company-admin`.
- لوحة «قرارات اليوم» في Control Pass (عربي كامل).
- ربط كل تقرير في المنصة بـ **PDF موحّد** (فواتير، زيارات، حوادث، امتثال).

---

## 4. التقارير: PDF + بريد إلكتروني

**المطلوب:** كل تقرير يُرسل للمستخدم كـ **PDF مرفق**.

| التقرير | PDF اليوم | إرسال بريد |
|---------|-----------|------------|
| فواتير | ✅ ReportLab | ✅ عند الإرسال |
| تذكير دفع | ✅ | ✅ |
| تقرير تشغيل (Ops) | ✅ جديد | ✅ زر «PDF per E-Mail» |
| تصدير شركات / مستندات | جزئي | قيد التوحيد |
| Enterprise / Ops Center | JSON | → PDF في المرحلة 2 |

**API:** `POST /api/reporting/email-pdf` — يتطلب SMTP في الإعدادات أو Railway.

---

## 5. التوقيع على بطاقة العامل (جهاز لاحق)

**الوضع الحالي:** حقل `compliance_signature_data` (PNG) عند تسليم البطاقة في الإدارة.

**الجاهزية للجهاز الخارجي:**

1. جهاز توقيع USB/Tablet يرسل `POST /api/device/signature` (مقترح) أو WebSocket محلي.
2. Agent على PC المكتب ينقل التوقيع إلى API المنصة.
3. ربط التوقيع بـ `worker_id` + `captured_at` + `device_id` للتدقيق.

لا حاجة لتغيير البطاقة الرقمية — التوقيع يُخزَّن في سجل العامل والتدقيق.

---

## 6. الكاميرا والتعرف على الوجه

**الوضع الحالي:**

- `POST /api/integrations/security-cameras/events`
- `POST /api/ops-os/cameras/analyze`
- جدول `camera_ai_events`

**عند توصيل الكاميرا:**

1. تسجيل `camera_id` لكل موقع في الإعدادات.
2. إرسال لقطة أو حدث إلى الـ API (Webhook أو RTSP Bridge صغير).
3. مطابقة الوجه مع `workers.photo_data` (مرحلة 2: Azure Face / موديل محلي على السحابة الخاصة).

---

## 7. السحابة الخاصة (حكومي / On-Prem)

**جاهز تقنياً عبر:**

- Docker + `backend/server.py`
- PostgreSQL (`BAUPASS_PG_RUNTIME=1`)
- تخزين ملفات `DOCS_UPLOAD_DIR` على قرص مشفّر
- متغيرات بيئة فقط (بدون اعتماد على Railway)

**مقترح نشر حكومي:**

```text
Kubernetes (أو VM) → Ingress TLS → BauPass API
                 → PostgreSQL HA
                 → Redis (RQ jobs)
                 → Object Storage (S3-compatible)
```

عزل شبكة، VPN، نسخ احتياطي يومي — موثّق في `docs/postgres-cutover-runbook.md` و `docs/enterprise-backup-restore-runbook.md`.

---

## 8. التكامل مع الأنظمة الأخرى

| النظام | التكامل |
|--------|---------|
| DATEV | OAuth + CSV |
| Microsoft 365 / Google | OAuth في Enterprise |
| SAP / Oracle | معاينة تصدير |
| Webhooks | منصة API للأحداث |
| البريد (IMAP) | صندوق مستندات |

**للوزارات:** واجهة **Integration Hub** + عقود API + سجل تدقيق (Audit) لكل حدث.

---

## 9. خارطة طريق مقترحة (12 شهراً)

### المرحلة أ — 0–3 أشهر (استقرار + مؤسسات)

- [ ] كل التقارير → PDF + بريد مجدول
- [ ] واجهة عربية كاملة في تطبيق العامل والإدارة
- [ ] اختبارات قبول (UAT) لكل دور
- [ ] Runbook نسخ احتياطي + استعادة

### المرحلة ب — 3–6 أشهر (أجهزة)

- [ ] SDK توقيع USB/Tablet
- [ ] Bridge كاميرا RTSP → `camera_ai_events`
- [ ] Face match اختياري (خاصية Enterprise)

### المرحلة ج — 6–12 شهراً (حكومة + SaaS)

- [ ] Helm Chart للسحابة الخاصة
- [ ] SSO حكومي (SAML/OIDC)
- [ ] تصنيف أمني / ISO 27001 documentation pack
- [ ] Marketplace تكاملات (DATEV, HR, ERP)

---

## 10. لماذا يمكن أن تتفوّق على السوق

1. **بناء + امتثال + تشغيل** في منصة واحدة (ليس HR فقط ولا تسجيل دخول فقط).
2. **Physical Operations OS** — خريطة موقع، طوارئ، سمعة، IoT.
3. **قرارات آلية** وليس لوحات فقط.
4. **جاهزية حكومية** — tenant، سحابة خاصة، تدقيق، لغات.
5. **تجربة العامل** — PWA، Offline، QR، محفظة، Lohn-PDF.

---

## 11. خطواتك الفورية

1. ضبط **SMTP** على Railway لإرسال PDF.
2. تجربة **PDF per E-Mail** من لوحة Reporting.
3. مراجعة **/api/ops/guidance** في Dashboard.
4. لـ DATEV: إضافة `DATEV_CLIENT_*` ثم «DATEV verbinden».
5. للتأجير الحكومي: عرض PoC على **سحابة خاصة** + وثيقة أمان.

---

*آخر تحديث: يتوافق مع فرع `main` بعد ميزات Lohn, White-Label, OCR, Notifications, PDF Email.*
