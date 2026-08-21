# خطة استيراد النظام الكامل (Phase A أولاً)

## الهدف

تمكين **استيراد نظام شركة كاملة** إلى SUPPIX بدون فقدان بيانات (موظفين، عقود عمل، مستندات، حضور، فواتير، خطط نشر…)، مع:
- تحقق متعدد المرّات
- نسبة إنجاز واضحة (مثلاً 90% / 100%)
- تنظيم البيانات داخل النظام بعد الاستيراد
- **التصدير الكامل لاحقاً** (Phase C) بنفس الصيغة حتى تكتمل الحلقة

سيناريو المستخدم: تأجير النظام لشركة كانت على نظام قديم — يجب ألا تفقد بيانات موظفيها.

---

## الوضع الحالي (ما يوجد فعلاً)

| العنصر | الواقع |
|--------|--------|
| أزرار UI | `index.html` → `#importButton` / `#exportButton` (قائمة Mehr) |
| Frontend | `app.js` → `handleTopbarImport` / `handleTopbarExport` |
| API | `GET /api/export` · `POST /api/import` في `backend/server.py` |
| الصيغة | JSON `schemaVersion: 2026-04-export-v2` |
| الاستيراد اليوم | فقط: `companies`, `subcompanies`, `workers`, `access_logs`, `invoices` |
| ناقص حرج | عقود `employment_contracts`، مستندات `worker_documents` (+ملفات)، خطط نشر، مستخدمي الشركة، إعدادات الشركة، … |
| Dry-run | موجود جزئياً |
| Rollback | `create_import_rollback_backup()` موجود |
| نسخة SQLite كاملة | موجودة لكنها للمنصة كلها وليست هجرة شركة |

الخلاصة: الاستيراد **حقيقي لكنه ناقص** — لا يكفي لسيناريو «تأجير نظام بلا فقدان بيانات».

---

## القرار المعماري

1. **صيغة أرشيف جديدة** `schemaVersion: 2026-08-transfer-v1` كملف **ZIP** (وليس JSON مسطح فقط).
2. الإبقاء على `/api/import` القديم للـ JSON القديم (توافق خلفي).
3. مسار جديد للاسترداد الكامل:
   - `POST /api/transfer/import/validate` — فحص الحزمة + dry-run
   - `POST /api/transfer/import/start` — بدء الاستيراد (وظيفة خلفية)
   - `GET /api/transfer/import/<job_id>` — تقدّم + تقرير تحقق
4. وحدة جديدة: `backend/app/platform/transfer/` (لا تضخيم `server.py`).
5. Phase A = نطاق تأجير الشركة (الأهم). Export الكامل في Phase C بنفس الـ ZIP.

---

## صيغة الأرشيف (ZIP)

```
workpass-transfer-v1.zip
├── manifest.json          # schemaVersion, companyId, createdAt, domains[], counts, sha256
├── checksums.sha256       # لكل ملف داخل الأرشيف
├── domains/
│   ├── companies.json
│   ├── subcompanies.json
│   ├── workers.json
│   ├── employment_contracts.json
│   ├── contract_templates.json
│   ├── worker_documents.json      # metadata فقط
│   ├── access_logs.json
│   ├── invoices.json
│   ├── deployment_days.json
│   └── leave_requests.json        # إن وُجدت
└── files/
    ├── worker_photos/<worker_id>.jpg
    ├── worker_documents/<doc_id>/...
    └── contracts/<contract_id>.pdf
```

قواعد:
- كل صف يحمل `id` مستقراً + `company_id`.
- الملفات مربوطة بمسارات نسبية داخل `files/` + SHA-256 في الـ manifest.
- لا أسرار تشغيل (SMTP passwords, API keys, HCE secrets) في Phase A — تُستثنى صراحةً ويُبلَّغ عنها في التقرير.

---

## Phase A — نطاق الاستيراد (تأجير شركة)

### داخل النطاق
1. الشركة + العلامة التجارية الأساسية (`companies`)
2. الفروع (`subcompanies`)
3. الموظفون + الصور (`workers` + photos)
4. قوالب وعقود العمل (`contract_templates`, `employment_contracts`, events/sign sessions الأساسية)
5. مستندات الموظف وملفاتها (`worker_documents` + files)
6. سجلات الوصول (`access_logs`)
7. الفواتير الأساسية (`invoices`)
8. خطة النشر الشهرية (`worker_deployment_days` وما يلزمها)
9. طلبات الإجازة إن وُجدت في الجداول الحالية
10. محرك تحقق + تقرير نسبة إنجاز + UI تقدّم

### خارج النطاق (Phase B لاحقاً)
- دردشة، أجهزة، كاميرات، محرر المستندات الكامل، مستخدمو الشركة/كلمات المرور، كشوف رواتب Lohn التفصيلية، HCE/trust، أرشيف ضخم جداً

### التصدير الكامل
- Phase C: `GET /api/transfer/export?company_id=…` يُنتج نفس ZIP الذي يقرأه المستورد.

---

## الوحدة الخلفية المقترحة

```
backend/app/platform/transfer/
  __init__.py
  schema.py           # manifest + schemaVersion
  archive.py          # open ZIP, checksums, stream files
  job_store.py        # حالة الوظيفة + نسبة التقدّم
  verifier.py         # 4 مرّات تحقق → completionPercent
  handlers/
    base.py           # extract / validate / apply / verify
    companies.py
    workers.py
    contracts.py
    documents.py
    access_logs.py
    invoices.py
    deployment.py
  routes.py           # Flask blueprint
  service.py          # orchestration
```

تسجيل الـ blueprint عبر المسار الموجود لتسجيل منصّة الـ API.

كل handler يطبّق نفس العقد:
1. `extract(archive)` → صفوف + ملفات
2. `validate(rows, ctx)` → أخطاء/تحذيرات
3. `apply(db, rows, files, ctx)` → كتابة منظّمة (معاملة لكل نطاق أو دفعات)
4. `verify(db, expected)` → عدّاد + عيّنات

---

## محرك التحقق (4 مرّات)

| المرّة | ماذا تفحص | وزن تقريبي |
|--------|-----------|------------|
| 1 | أعداد الصفوف لكل نطاق مقابل الـ manifest | 40% |
| 2 | سلامة المراجع (worker.company_id، contract.worker_id، document.worker_id، …) | 25% |
| 3 | عيّنة محتوى (hash لـ N صفوف عشوائية / حقول حاسمة) | 20% |
| 4 | تطابق SHA-256 لملفات `files/` بعد التخزين | 15% |

النتيجة النهائية:
```json
{
  "completionPercent": 97,
  "status": "partial|complete|failed",
  "passes": { "counts": {...}, "refs": {...}, "samples": {...}, "files": {...} },
  "missing": [...],
  "warnings": [...]
}
```

قواعد العرض للمستخدم:
- **100%** فقط إذا مرّت كل المرّات بلا نواقص إلزامية
- **90–99%** نواقص غير حرجة أو ملفات اختيارية ناقصة (تظهر في التقرير)
- **&lt;90%** لا يُعتبر الاستيراد ناجحاً — يُعرض Rollback مقترح

قبل التطبيق: نسخة احتياطية تلقائية (توسيع `create_import_rollback_backup` أو SQLite snapshot للشركة حيث أمكن).

---

## واجهة المستخدم (استيراد)

تحسين مسار زر **System importieren**:
1. اختيار ملف `.zip` (أو JSON قديم → مسار التوافق)
2. شاشة **Validate / Dry-run** تعرض الأعداد المتوقعة لكل نطاق
3. تأكيد صريح (شركة الهدف / إنشاء شركة جديدة / دمج بحذر)
4. شريط تقدّم حيّ: النطاق الحالي + النسبة الإجمالية
5. تقرير نهائي: «تم إسقاط النظام 100%» أو «90%» مع قائمة النواقص

الملفات الأساسية للواجهة:
- `app.js` (`handleTopbarImport`, حوار جديد للتقدّم)
- نصوص i18n في `app.js` / `app-i18n-extra-langs.js` (DE/EN/AR على الأقل في A)

---

## مراحل التنفيذ العملية (Phase A)

| # | حزمة عمل | مخرجات |
|---|----------|--------|
| 1 | Schema + archive reader/writer | قراءة ZIP + checksums |
| 2 | Job store + APIs validate/start/status | تقدّم قابل للاستعلام |
| 3 | Handlers: companies / subcompanies / workers(+photos) | أساس الشركة والموظفين |
| 4 | Handlers: contracts + templates + PDFs | عقود العمل |
| 5 | Handlers: worker_documents + files | المستندات على القرص |
| 6 | Handlers: access_logs + invoices + deployment | التشغيل اليومي |
| 7 | Verifier 4-pass + completionPercent | تقرير موثوق |
| 8 | UI progress + dry-run + تقرير نهائي | زر الاستيراد جاهز للاستخدام |
| 9 | اختبارات | انظر أدناه |

التصدير المطابق (Phase C) يُنفَّذ بعد استقرار المستورد حتى لا نثبت صيغة ناقصة.

---

## معايير النجاح (Phase A)

- [ ] استيراد شركة تجريبية بكل نطاقات A بدون فقدان صف إلزامي
- [ ] العقود مرتبطة بالموظفين الصحيحين وتظهر في `admin-v2/contracts`
- [ ] ملفات المستندات قابلة للتنزيل بعد الاستيراد
- [ ] التقرير يعرض نسبة إنجاز حقيقية (ليست شريط وهمي)
- [ ] Dry-run لا يكتب في قاعدة البيانات
- [ ] فشل مرّة تحقق حرجة → لا يُعلَن 100%
- [ ] JSON القديم `2026-04-export-v2` ما زال يعمل كما هو
- [ ] Superadmin فقط للمسار الكامل في A
- [ ] اختبارات وحدة للـ verifier + اختبار تكامل لأرشيف صغير

---

## خطة الاختبار

1. **Unit**: checksums، عدّ النسب، فشل مرجع عقد بلا موظف
2. **Integration**: ZIP صغير (شركة + 3 موظفين + عقد + مستند) → verify 100%
3. **Negative**: ملف تالف / checksum خاطئ / شركة محظورة → رفض واضح
4. **Compat**: استيراد JSON القديم لا ينكسر
5. **Manual**: من زر Mehr → System importieren → تقرير نهائي

---

## مخاطر وضوابط

- `INSERT OR REPLACE` الحالي قد يستبدل صفوفاً موجودة — في A: وضعان صريحان: `create_new_company` أو `merge_into_company` مع تقرير تعارضات قبل الكتابة.
- الملفات الكبيرة: استيراد دفعات + وظيفة خلفية (RQ إن كان متاحاً، وإلا thread + job_store).
- لا استيراد كلمات مرور/أسرار أجهزة في A.
- PostgreSQL و SQLite: handlers تستخدم طبقة DB الحالية فقط.

---

## ترتيب التسليم للمستخدم

1. **الآن (بعد الموافقة على الخطة):** تنفيذ Phase A — الاستيراد الكامل لنطاق التأجير + تحقق + نسبة إنجاز.
2. **بعدها:** Phase B لتوسيع النطاقات.
3. **ثم:** Phase C — تصدير بنفس الـ ZIP ليكتمل «تصدير ↔ استيراد» بلا فقدان.

---

## ملفات محورية للمس

- `backend/server.py` — الإبقاء على الاستيراد القديم؛ ربط خفيف إن لزم
- `backend/app/platform/transfer/*` — جديد
- `backend/app/domains/contracts/*` — مرجع لشكل العقود
- `backend/app/domains/workers/*` — مرجع للموظفين/المستندات
- `app.js` + `index.html` — زر الاستيراد وتجربة التقدّم
