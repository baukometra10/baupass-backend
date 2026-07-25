# خطة: محرر مستندات مدمج في WorkPass (شبيه بـ Word / أذكى منه في السياق التشغيلي)

> **القرار الموصى به:** لا نبني «نسخة مايكروسوفت وورد كاملة». نبني **محرر مستندات مؤسسي داخل المنصة** (إنشاء، تحرير، اقتراحات، قوالب، توقيع، PDF، تدقيق) مربوط بالعمال والشركات والعقود والامتثال.  
> التوافق الكامل مع `.docx` المتقدم يُضاف لاحقاً عبر محرك خارجي (OnlyOffice/Collabora) إذا طلب العملاء ذلك صراحة.

> **فصل عن العقود (مهم):** صفحة **عقود العمل موجودة وتبقى المصدر الوحيد لدورة العقد** (قالب، راتب، قفل مالك، توقيع، PDF عقد). المحرر العام في `/admin-v2/docs.html` يعمل وضعاً عاماً + ربطاً اختيارياً؛ زر **Rich-Editor** في العقود يفتح نفس المحرك دون استبدال صفحة العقود.

## حالة التنفيذ (محدّث 2026-07-24)

**ترتيب الأولويات من المستخدم: 1→2→3→4**
1. إحساس وورد (جداول، هوامش، رأس/تذييل، أنماط، شريط Ribbon)
2. المحرر داخل صفحة العقود
3. OnlyOffice لتوافق DOCX الحقيقي
4. تكامل النظام (موظف → مستند → اعتماد → أرشفة → إشعار)

### Branding + مشاركة مستقلة
- ✅ دمج براندينج الشركة (شعار، اسم، عنوان، بريد، اتصال) في merge-context
- ✅ زر **Briefkopf auf Papier setzen** + تطبيق تلقائي للمستندات الجديدة
- ✅ PDF يحمل شعار/تذييل الشركة
- ✅ قائمة موظفي الشركة أوضح + مشاركة بدون MA: PDF / Drucken / E-Mail
- ✅ إرسال للموظف يبقى اختيارياً (خطوة 3)

### W5 — تصدير PDF من السيرفر + أرشفة PDF عند الاعتماد
- ✅ `backend/app/platform/reports/editor_pdf.py` (ReportLab / A4)
- ✅ `GET /api/v2/docs/<id>/export?format=pdf`
- ✅ زر **PDF** في الشريط + تصدير من الواجهة
- ✅ **Freigeben → MA** يحفظ PDF في `worker_documents` (مع fallback إلى HTML)
- ✅ Word-Export يفضّل `.docx` الحقيقي عند توفر `build_docx_bytes`

### W4 — تكامل النظام (موظف → اعتماد → أرشفة → إشعار)
- ✅ زر **Schreiben** من قائمة الموظفين → `docs.html?worker_id=`
- ✅ حالات: `draft` / `in_review` / `approved` / `archived`
- ✅ **Freigeben → MA**: أرشفة في `worker_documents` + Mitteilung
- ✅ API: `POST /docs/<id>/status`, `POST /docs/<id>/publish`

### W3 — OnlyOffice
- ✅ `backend/app/domains/docs/onlyoffice.py` — JWT + DOCX + config/callback
- ✅ API: `/onlyoffice/status|config|file|callback`
- ✅ UI زر **Word Pro** + Overlay في `docs.html`
- ✅ `deploy/onlyoffice/docker-compose.yml` + `deploy/start-onlyoffice.ps1`
- ✅ `start-lokal.ps1` يضبط `ONLYOFFICE_*`
- ⏳ يتطلب Docker Desktop محلياً (حالياً غير مثبت على الجهاز)

### سابق (أساس)
- ✅ Migration `043`/`044` + domain `/api/v2/docs*`
- ✅ Merge / versions / AI suggest / export HTML·DOC
- ✅ جسر Rich-Editor من العقود (يفتح docs منفصلاً — سيُستبدل بـ W2)

---

## 1) ماذا يريد المنتج فعلياً؟

| حاجة الشركة | كيف يخدمها المحرر داخل النظام |
|-------------|-------------------------------|
| كتابة خطاب إنذار / شهادة / تعليمات سلامة | مستند مربوط بـ `company_id` + `worker_id` + نوع المستند |
| عقود وتعديلات | نفس المحرر يحرّر `body_template` / نص العقد قبل التصدير PDF |
| اقتراحات وتصحيح | طبقة Suggestions + AI Copilot (موجود جزئياً عبر OpenAI) |
| مراجعة قانونية / مدير | تعليقات، حالات مسودة→مراجعة→معتمد، Audit |
| أرشفة وامتثال | إصدارات، PDF موقّع، صلاحيات RBAC، عزل المستأجر |

**ليس الهدف:** استبدال Word للأعمال المكتبية العامة خارج WorkPass.  
**الهدف:** أن تكون «أوراق الشركة» جزءاً من دورة الهوية/الامتثال/التشغيل.

---

## 2) ثلاثة مسارات التقنية (والاختيار)

### أ) محرر أصلي مدمج — **الموصى به للمرحلة 1–3**
- **الواجهة:** TipTap (ProseMirror) داخل `admin-v2` (وواجهة عامل لاحقاً للقراءة/التوقيع فقط).
- **التخزين:** JSON للمستند (ProseMirror doc) + HTML للعرض + PDF عند الاعتماد.
- **الاقتراحات:** تعليقات/اقتراحات كتطبيق منصة (جدول DB)، وليس كـ Word Track Changes كامل في البداية.
- **AI:** استدعاء `/api/ai/query` أو endpoint جديد `/api/docs/suggest` بسياق الشركة/العامل.
- **التصدير:** PDF عبر مسار العقود الحالي (ReportLab/HTML→PDF) + لاحقاً DOCX بسيط.

**لماذا يناسب WorkPass:** نفس stack (Flask + admin-v2 vanilla/JS)، عزل مستأجرين، ربط سهل بالعقود والعمال، بدون تشغيل خدمة Java ثقيلة.

### ب) OnlyOffice / Collabora (محرك وورد حقيقي)
- خادم مستقل + iframe في Admin.
- أفضل توافق DOCX، لكنه تشغيل/ترخيص/أمن أثقل (شبكة، JWT، تخزين مشترك).
- **يُؤجَّل** إلى مرحلة Enterprise إذا عملاء كثر يطلبون «افتح لي نفس ملف Word».

### ج) تضمين Microsoft 365 / Google Docs
- تكامل OAuth موجود جزئياً (M365/Google).
- المستند يعيش خارج المنصة → ضعف في الامتثال والتدقيق الموحّد.
- مناسب كـ **خيار ربط** وليس كمحرك أساسي.

**التوصية:** ابدأ بـ **(أ)**، صمّم واجهة تخزين محايدة بحيث يمكن لاحقاً فتح نفس المستند في OnlyOffice دون إعادة بناء الدومين.

---

## 3) كيف يُدمَج كجزء من النظام (وليس منتجاً منفرداً)

```text
[Admin-v2 Docs Editor] ──► /api/v2/docs/*
         │                      │
         │                      ├─ workers / companies / sites (merge fields)
         │                      ├─ contracts (templates + signing)
         │                      ├─ worker_documents (archive + expiry)
         │                      ├─ inbox / mitteilungen (notify)
         │                      ├─ audit + RBAC + tenant
         │                      └─ AI suggest + PDF export
         ▼
   Worker App: عرض / توقيع فقط (لا تحرير كامل في الحقل)
```

### كيانات مقترحة (DB)
- `company_documents` — id, company_id, title, doc_type, status, current_version_id, worker_id?, site_id?, created_by, …
- `company_document_versions` — id, document_id, version, content_json, content_html, created_by, created_at
- `company_document_comments` — اقتراحات/تعليقات (anchor في المستند، status: open/accepted/rejected)
- `company_document_templates` — قوالب قطاعية (بناء، طيران، …) مع `{{worker.name}}` وغيرها
- ربط اختياري: `contract_id` أو `worker_document_id` بعد الاعتماد

### أنواع مستندات أولوية (MVP) — **خارج دورة عقد العمل**
1. خطاب / Mitteilung للموظف  
2. تعليمات سلامة / موقع  
3. شهادة / تأكيد حضور  
4. سياسات داخلية / نماذج تشغيل  

**صراحة خارج النطاق كمنتج موازٍ:** إنشاء عقد عمل، تعديل راتب، قفل المالك، مسار التوقيع القانوني للعقد — تبقى في `admin-v2/contracts.*` فقط.

**تحسين العقود لاحقاً (اختياري):** استبدال محرر النص الخام في صفحة العقود بنفس محرك TipTap كـ widget داخلي — نفس الصفحة، نفس API العقود، بدون قسم «مستندات = عقود».

---

## 4) طريقة البناء (مراحل تنفيذ)

### المرحلة 0 — قرارات منتج (قبل كود كثير)
- من يحرّر؟ (company-admin فقط أم أدوار أضيق)
- هل العامل يحرّر أم يوقّع فقط؟
- هل نحتاج تحرير متزامن متعدد المستخدمين في v1؟ (**لا** — احفظ/اقفل أوقترح لاحقاً Yjs)

### المرحلة 1 — MVP محرر + تخزين (2–4 أسابيع)
1. Domain جديد: `backend/app/domains/docs/` (routes + service + repository) على نمط contracts.
2. TipTap في صفحة `admin-v2/docs.html` (أو تبويب داخل Betrieb).
3. CRUD مسودة + حفظ إصدارات.
4. Merge fields بسيطة: اسم العامل، الشركة، التاريخ، الموقع.
5. تصدير PDF أولي (إعادة استخدام أنماط `contracts_pdf` قدر الإمكان).
6. Audit: create/update/publish.

### المرحلة 2 — اقتراحات + AI (2–3 أسابيع)
1. تعليقات/اقتراحات مربوطة بـ range في المستند.
2. زر «تحسين الصياغة / تلخيص / ترجمة DE↔AR» عبر AI الموجود.
3. اقتراحات سياقية من بيانات المنصة: «وثيقة العامل تنتهي خلال 7 أيام — أدرج فقرة تذكير».
4. حالات workflow: `draft → in_review → approved → archived`.

### المرحلة 3 — ربط الامتثال والعقود (2–3 أسابيع)
1. عند الاعتماد: إنشاء/تحديث سجل في `worker_documents` أو إرفاق بالعقد.
2. توقيع عبر جسر التوقيع الموجود (`compliance_signature` / device signature).
3. قوالب عقود تنتقل من نص خام إلى TipTap template.
4. إشعار Inbox + بريد PDF.

### المرحلة 4 — DOCX والتوافق مع Word (اختياري)
1. استيراد DOCX→JSON (mammoth / docx lib) محدود الأنماط.
2. تصدير DOCX بسيط.
3. إن طُلب توافق عالي: نشر OnlyOffice Document Server + فتح نفس `company_documents` عبر JWT.

### المرحلة 5 — تعاون حي (لاحقاً فقط)
- Yjs + WebSocket الموجود في المنصة للتحرير المتزامن.
- لا تبدأ به؛ يزيد التعقيد دون قيمة MVP.

---

## 5) واجهات API المقترحة

```http
GET    /api/v2/docs?company_id=
POST   /api/v2/docs
GET    /api/v2/docs/{id}
PUT    /api/v2/docs/{id}                 # حفظ محتوى + نسخة جديدة إن لزم
POST   /api/v2/docs/{id}/publish
POST   /api/v2/docs/{id}/export.pdf
POST   /api/v2/docs/{id}/suggest         # AI
GET/POST /api/v2/docs/{id}/comments
POST   /api/v2/docs/{id}/comments/{cid}/accept
GET    /api/v2/docs/templates
POST   /api/v2/docs/from-template
```

كل المسارات: `@require_auth` + عزل شركة + (لاحقاً) قفل حساس مثل العقود إن احتوى رواتب.

---

## 6) تجربة المستخدم (باختصار)

1. Betrieb → **Dokumente** → «Neues Dokument» أو من بطاقة موظف «Schreiben…».
2. اختيار قالب + ربط موظف/موقع.
3. تحرير TipTap (عناوين، قوائم، جداول بسيطة، شعار الشركة).
4. شريط جانبي: اقتراحات AI + تعليقات المراجعين + حقول الدمج.
5. اعتماد → PDF + أرشفة + إشعار.

هذا يجعل المحرر **قناة تشغيل** داخل WorkPass، لا مكتباً منفصلاً.

---

## 7) مخاطر وحدود صادقة

| الخطر | التخفيف |
|-------|---------|
| توقعات «مثل Word 100%» | رسائل منتج واضحة: محرر مؤسسي للمستندات التشغيلية؛ Word الكامل اختياري لاحقاً |
| جداول/رؤوس معقدة | ابدأ بأنماط محدودة؛ الجداول المتقدمة في مرحلة DOCX/OnlyOffice |
| أمن AI يسرّب بيانات | لا ترسل رواتب/SSR إلا مع قفل العقود؛ سجل audit لكل suggest |
| حجم `server.py` | Domain منفصل `docs/` من اليوم الأول |
| أداء حفظ كبير | إصدارات عند publish أو كل N دقائق، وليس كل ضغطة حرف عبر السيرفر |

---

## 8) معايير نجاح المرحلة 1

- إنشاء خطاب لموظف من قالب خلال &lt; 2 دقيقة.
- حفظ مسودة + إعادة فتح بنفس التنسيق.
- تصدير PDF مقروء (DE/AR أساسي).
- المستند يظهر في سياق الشركة/الموظف وليس كملف يتيم.
- لا كسر لعقود/رفع المستندات الحالي.

---

## 9) الخطوة التالية المقترحة

بعد موافقتك على النطاق:
1. تثبيت قرار: **TipTap-first** (نعم/لا) وهل العامل يوقّع فقط.
2. تصميم migration للجداول أعلاه.
3. Skeleton: `docs` domain + صفحة admin-v2 فارغة بمحرر Hello World مربوط بشركة تجريبية.

---

## قرارات مفتوحة (للمستخدم)

1. هل الأولوية الأولى: **خطابات/سياسات** أم **تحرير نص العقود** داخل نفس المحرر؟
2. هل تحتاجون **تحرير متزامن** (شخصان في نفس المستند) في السنة الأولى؟
3. هل التوافق الكامل مع ملفات Word للعملاء إلزامي عند الإطلاق أم يكفي PDF + استيراد لاحق؟
