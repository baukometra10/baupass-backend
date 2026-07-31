# جسر WorkPass Lohn — عقد العزل الإلزامي

اسم المنتج: **WorkPass Lohn** · SUPPIX AI · WorkPass Lohn-Buchhaltung (Standalone)

## ربط مرة واحدة + تفعيل اختياري لكل شركة

سوبر أدمن يضبط الربط العام مرة واحدة (`platform-link`).

**WorkPass Lohn اختياري لكل شركة**:
- إذا كان `platform-link` مفعّلاً مع Auto-Provision: عند إنشاء شركة تُرسل تلقائياً إلى Lohn مع **اسم المستخدم وكلمة المرور**
- أو عبر مربع الاختيار / `"workpassLohnEnabled": true`
- سحب بيانات الدخول من Lohn: `GET /api/v2/accounting/company/access`
- كشوف الأجور ترجع عبر `POST /api/v2/accounting/statements` ثم موافقة بشرية قبل إرسالها للموظف
- من الإعدادات لاحقاً:

```http
PUT /api/payroll/accounting/company-settings
{ "companyId": "…", "workpassLohnEnabled": false }
```

Rechtliches لكل شركة: `PUT /api/companies/<id>/legal` (Impressum/Datenschutz).
حالة الربط العام تظهر في Ops Command Center.

عند الإيقاف: يتوقف إرسال الساعات/الـ webhook لهذه الشركة فوراً، ويمكنها استخدام برنامج محاسبة آخر.

---

## إلزامي عبر الـ API

| قاعدة | التفاصيل |
|---|---|
| `company.id` | مطلوب في كل رواتب / فواتير / تسجيل شركة — بدونها يُرفض الطلب |
| مفتاح الرواتب | `companyId::employeeId::period` (وليس الاسم) |
| مفتاح الفواتير | `companyId::رقم_الفاتورة` حتى لا تتصادم أرقام متشابهة بين الشركات |
| Header | `X-WorkPass-Company-Id` — كل قراءة/إصدار محدود بتلك الشركة فقط |
| سجل الشركات | `POST /v1/company/upsert` في WorkPass Lohn · مرآة المنصة: `POST /api/v2/accounting/company/upsert` |
| عزل | نفس رقم الموظف `1001` في شركتين = وظيفتان منفصلتان، بدون تسرّب |

في واجهة WorkPass Lohn: حقل **Firma-ID** في تبويب API-Bridge يفلتر الـ Inbox لتلك الشركة فقط.  
على المنصة: `Firma-ID` = `companies.id` (نفس القيمة في `X-WorkPass-Company-Id`).

## التدفق

1. المنصة تجمع ساعات الشهر + `hourly_rate` من العقد، مع `storageKey` و `company.id`.
2. WorkPass Lohn يسحب الساعات أو يستقبل Webhook `hours.ready`.
3. WorkPass Lohn يرفع الكشوفات مع `companyId` + `employeeId` بحالة `pending_approval`.
4. مسؤول الشركة / سوبر أدمن يؤكد → `lohnabrechnung` للموظف.

## Headers (WorkPass Lohn → المنصة)

| Header | مطلوب |
|---|---|
| `X-WorkPass-Company-Id` | نعم (بديل قديم: `X-Company-Id`) |
| `X-Accounting-Key` | نعم (`acc_live_…`) |
| `X-Suppix-Timestamp` / `X-Suppix-Signature` | عند التوقيع HMAC |

بدون `X-WorkPass-Company-Id` → `400 company_id_required`.

## مسارات المنصة

```http
GET  /api/v2/accounting/hours?period=2026-06
POST /api/v2/accounting/hours/ack
POST /api/v2/accounting/statements
GET  /api/v2/accounting/company
POST /api/v2/accounting/company/upsert
```

### صف ساعات (مثال)

```json
{
  "companyId": "lufthansa",
  "company": { "id": "lufthansa" },
  "employeeId": "w-1001",
  "workerId": "w-1001",
  "storageKey": "lufthansa::w-1001::2026-06",
  "period": "2026-06",
  "hours": 160,
  "hourlyRate": 15
}
```

إثبات العزل: `otherco::w-1001::2026-06` مفتاح مختلف تماماً عن `lufthansa::w-1001::2026-06`.

### رفع كشوفات

```json
{
  "companyId": "lufthansa",
  "period": "2026-06",
  "statements": [
    {
      "companyId": "lufthansa",
      "employeeId": "w-1001",
      "storageKey": "lufthansa::w-1001::2026-06",
      "hours": 160,
      "grossAmount": 2400,
      "pdfBase64": "…"
    }
  ]
}
```

كل صف بدون `companyId` يُرفض (`company_id_required`).  
`companyId` مخالف للهيدر → `403 company_id_mismatch`.

### دفعة الرواتب الشهرية (`platform.payroll.batch.v1`)

- **سحب (Pull):** `GET|POST /api/v2/accounting/payroll-batch?period=2026-07`
- **دفع (Push):** المنصة ترسل `POST {LOHN}/v1/payroll/batch` تلقائياً مع نفس الحمولة
- بعد الدفع يكفي في Lohn: «Nur Freigabe offener Jobs»

### بيانات ناقصة للموظف

- Lohn/Steuer → `POST /api/v2/accounting/employee-data-alerts`
- في Ops: بطاقة «Fehlende Mitarbeiterdaten» + زر **Gelesen / ausblenden**

### شركة (مرآة upsert)

```http
POST /api/v2/accounting/company/upsert
X-WorkPass-Company-Id: lufthansa
```

الجسم يجب أن يحتوي `id` / `companyId` مطابقاً للهيدر.

## حدود

- المنصة لا تحسب الضرائب/الصافي — ذلك في WorkPass Lohn.
- لا إرسال للموظفين قبل موافقة بشرية على المنصة.
