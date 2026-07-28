# جسر المحاسبة الخارجي (Accounting Bridge)

المنصة **لا** تضمّن تطبيق المحاسبة. التطبيق يبقى منفصلاً ويتبادل البيانات عبر API موقّع ومعزول لكل شركة.

## التدفق

1. المنصة تجمع ساعات الشهر من `access_logs` + `hourly_rate` من عقد العمل.
2. تطبيق المحاسبة يسحب الساعات (`GET`) أو يستقبل Webhook `hours.ready`.
3. المحاسبة تحسب الكشوفات وترفعها (`POST /statements`) بحالة `pending_approval`.
4. مسؤول الشركة أو السوبر أدمن يؤكد الإرسال.
5. بعد التأكيد فقط: `lohnabrechnung` تصل للموظف + Push/Mitteilung.

## إعداد التكامل (أدمن)

```http
POST /api/payroll/accounting/integration
Authorization: Bearer <session>
Content-Type: application/json

{
  "companyId": "…",          // سوبر أدمن فقط
  "webhookUrl": "https://accounting.example/hooks/suppix-hours",
  "enabled": true,
  "runDay": 1,
  "rotateKey": true
}
```

الاستجابة تعرض مرة واحدة فقط: `apiKey` (`acc_live_…`) و `signingSecret`.

## API لتطبيق المحاسبة

Headers:

| Header | مطلوب | معنى |
|---|---|---|
| `X-Company-Id` | نعم | معرّف الشركة |
| `X-Accounting-Key` | نعم | المفتاح `acc_live_…` |
| `X-Suppix-Timestamp` | عند التوقيع | Unix seconds |
| `X-Suppix-Signature` | اختياري | HMAC-SHA256 لـ `{timestamp}.{raw_body}` بالمفتاح `signingSecret` |

### سحب الساعات

```http
GET /api/v2/accounting/hours?period=2026-06
X-Company-Id: c1
X-Accounting-Key: acc_live_…
```

الحقول المهمة لكل صف: `workerId`, `hours`, `hourlyRate`, `grossEstimate` (تقديري فقط), `payBasis`.

### تأكيد الاستلام

```http
POST /api/v2/accounting/hours/ack
{
  "period": "2026-06",
  "fingerprint": "…"
}
```

### رفع كشوفات الحساب

```http
POST /api/v2/accounting/statements
{
  "period": "2026-06",
  "externalRef": "run-42",
  "statements": [
    {
      "workerId": "w1",
      "hours": 160,
      "hourlyRate": 15,
      "grossAmount": 2400,
      "netAmount": 1850,
      "currency": "EUR",
      "filename": "lohn_2026-06_w1.pdf",
      "pdfBase64": "<base64-pdf>"
    }
  ]
}
```

الحالة بعد الرفع: `pending_approval` — **لا إرسال للموظفين تلقائياً**.

### Webhook صادر من المنصة

عند يوم التشغيل (`runDay`) أو `export-now` مع webhook:

```json
{
  "event": "hours.ready",
  "companyId": "c1",
  "period": "2026-06",
  "exportId": "phe-…",
  "fingerprint": "…",
  "pullUrl": "/api/v2/accounting/hours?period=2026-06"
}
```

Headers: `X-Suppix-Timestamp`, `X-Suppix-Signature`, `X-Suppix-Event`.

## موافقة على المنصة

```http
GET  /api/payroll/statements/pending
GET  /api/payroll/statements/{batchId}
POST /api/payroll/statements/{batchId}/approve
POST /api/payroll/statements/{batchId}/reject
```

الأدوار: `company-admin`, `superadmin` (عزل الشركة لمسؤول الشركة).

تشغيل يدوي للتصدير:

```http
POST /api/payroll/accounting/export-now
{ "period": "2026-06", "notify": true }
```

## حدود

- المنصة لا تحسب الضرائب/التأمينات/الصافي النهائي.
- لا دمج كود المحاسبة داخل الريبو.
- لا إرسال كشوفات للموظفين قبل موافقة بشرية.
