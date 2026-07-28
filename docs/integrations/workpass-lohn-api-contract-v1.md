# WorkPass Lohn ↔ SUPPIX Platform — API Contract (v1)

**Base URL (production):** `https://<YOUR-PLATFORM-HOST>`  
**Product:** WorkPass Lohn (standalone) ↔ WorkPass / SUPPIX platform  
**Auth model:** per-company API key + mandatory company header (tenant lock)

Give this document to the accounting app. No other secrets are required from you beyond one `apiKey` per Firma.

---

## 0) One-time setup (platform admin)

```http
POST /api/payroll/accounting/integration
Authorization: Bearer <admin-session>
Content-Type: application/json

{
  "companyId": "<FIRMA-ID>",
  "enabled": true,
  "runDay": 1,
  "webhookUrl": "https://<WORKPASS-LOHN-HOST>/hooks/suppix-hours",
  "rotateKey": true
}
```

Response (store once — shown only now):

```json
{
  "ok": true,
  "integration": {
    "company_id": "<FIRMA-ID>",
    "apiKey": "acc_live_…",
    "signingSecret": "…",
    "api_key_prefix": "acc_live_…",
    "webhook_url": "https://…",
    "run_day": 1,
    "enabled": 1
  }
}
```

In WorkPass Lohn → **API-Bridge**:
- **Firma-ID** = `<FIRMA-ID>` (= platform `companies.id`)
- **API Key** = `apiKey`
- **Platform Base URL** = `https://<YOUR-PLATFORM-HOST>`

---

## 1) Mandatory rules (reject otherwise)

| Rule | Value |
|---|---|
| Company id | Required on every payroll / invoice / company call |
| Payroll storage key | `companyId::employeeId::period` |
| Invoice storage key | `companyId::invoiceNumber` |
| Tenant header | `X-WorkPass-Company-Id: <FIRMA-ID>` on **every** request |
| Isolation | Same employee number in two companies = two separate jobs |

Missing company header → `400 { "error": "company_id_required" }`  
Wrong company vs key → `401/403`

---

## 2) Headers (WorkPass Lohn → Platform)

```http
X-WorkPass-Company-Id: <FIRMA-ID>
X-Accounting-Key: acc_live_…
Content-Type: application/json
```

Optional HMAC (if you send signature, it is verified):

```http
X-Suppix-Timestamp: 1730000000
X-Suppix-Signature: <hmac_sha256_hex(signingSecret, "{timestamp}." + raw_body)>
```

Legacy alias accepted: `X-Company-Id` (prefer `X-WorkPass-Company-Id`).

---

## 3) Endpoints WorkPass Lohn must call

### 3.1 Pull monthly hours

```http
GET /api/v2/accounting/hours?period=2026-06
X-WorkPass-Company-Id: <FIRMA-ID>
X-Accounting-Key: acc_live_…
```

Example response:

```json
{
  "ok": true,
  "product": "WorkPass Lohn",
  "format": "suppix_workpass_lohn_hours_v1",
  "companyId": "<FIRMA-ID>",
  "company": { "id": "<FIRMA-ID>", "name": "Demo GmbH" },
  "period": "2026-06",
  "periodStart": "2026-06-01T00:00:00",
  "periodEnd": "2026-06-30T23:59:59",
  "rowCount": 1,
  "totalHours": 160,
  "totalGrossEstimate": 2400,
  "currency": "EUR",
  "tenantIsolation": "companyId::employeeId::period",
  "exportId": "phe-…",
  "fingerprint": "…",
  "rows": [
    {
      "companyId": "<FIRMA-ID>",
      "company": { "id": "<FIRMA-ID>" },
      "employeeId": "w-1001",
      "workerId": "w-1001",
      "storageKey": "<FIRMA-ID>::w-1001::2026-06",
      "badgeId": "B1",
      "firstName": "Ali",
      "lastName": "Hassan",
      "period": "2026-06",
      "hours": 160,
      "hourlyRate": 15,
      "salaryGrossMonthly": 0,
      "grossEstimate": 2400,
      "payBasis": "hourly",
      "currency": "EUR"
    }
  ]
}
```

Notes:
- `grossEstimate` is a **hint only** — WorkPass Lohn computes official payroll.
- `employeeId` / `workerId` = platform worker UUID/id (use this in `storageKey`, not the display name).

### 3.2 Ack hours received

```http
POST /api/v2/accounting/hours/ack
X-WorkPass-Company-Id: <FIRMA-ID>
X-Accounting-Key: acc_live_…

{
  "companyId": "<FIRMA-ID>",
  "period": "2026-06",
  "fingerprint": "…"
}
```

### 3.3 Push payslip batch (PDF)

```http
POST /api/v2/accounting/statements
X-WorkPass-Company-Id: <FIRMA-ID>
X-Accounting-Key: acc_live_…

{
  "companyId": "<FIRMA-ID>",
  "period": "2026-06",
  "externalRef": "lohn-run-42",
  "statements": [
    {
      "companyId": "<FIRMA-ID>",
      "employeeId": "w-1001",
      "workerId": "w-1001",
      "storageKey": "<FIRMA-ID>::w-1001::2026-06",
      "hours": 160,
      "hourlyRate": 15,
      "grossAmount": 2400,
      "netAmount": 1850,
      "currency": "EUR",
      "filename": "lohn_2026-06_w-1001.pdf",
      "pdfBase64": "<BASE64-PDF>"
    }
  ]
}
```

Response:

```json
{
  "ok": true,
  "batchId": "psb-…",
  "companyId": "<FIRMA-ID>",
  "period": "2026-06",
  "status": "pending_approval",
  "createdCount": 1,
  "statementIds": ["pst-…"],
  "errors": [],
  "tenantIsolation": "companyId::employeeId::period"
}
```

Important: status stays `pending_approval` until a **human** (company-admin / superadmin) approves on the platform. Then workers get `lohnabrechnung` + push.

### 3.4 Company registry (mirror of your `/v1/company/upsert`)

Pull:

```http
GET /api/v2/accounting/company
X-WorkPass-Company-Id: <FIRMA-ID>
X-Accounting-Key: acc_live_…
```

Upsert mirror (body `id` must match header):

```http
POST /api/v2/accounting/company/upsert
X-WorkPass-Company-Id: <FIRMA-ID>
X-Accounting-Key: acc_live_…

{ "id": "<FIRMA-ID>", "companyId": "<FIRMA-ID>" }
```

---

## 4) Webhook Platform → WorkPass Lohn (optional)

If `webhookUrl` is set, on monthly export the platform POSTs:

```http
POST https://<WORKPASS-LOHN-HOST>/hooks/suppix-hours
Content-Type: application/json
User-Agent: SUPPIX-WorkPass-Lohn-Bridge/1.0
X-Suppix-Event: hours.ready
X-Suppix-Product: WorkPass Lohn
X-WorkPass-Company-Id: <FIRMA-ID>
X-Suppix-Timestamp: 1730000000
X-Suppix-Signature: <hmac>

{
  "event": "hours.ready",
  "product": "WorkPass Lohn",
  "companyId": "<FIRMA-ID>",
  "company": { "id": "<FIRMA-ID>" },
  "period": "2026-06",
  "exportId": "phe-…",
  "fingerprint": "…",
  "rowCount": 12,
  "totalHours": 1840,
  "pullUrl": "/api/v2/accounting/hours?period=2026-06",
  "tenantIsolation": "companyId::employeeId::period"
}
```

Then WorkPass Lohn should `GET` the `pullUrl` (with auth headers).

---

## 5) Error codes

| HTTP | `error` | Meaning |
|---|---|---|
| 400 | `company_id_required` | Missing header or body company id |
| 400 | `invalid_period` | Period not `YYYY-MM` |
| 400 | `statements_must_be_array` | Bad body |
| 401 | `unauthorized` | Bad/missing API key for that company |
| 403 | `company_id_mismatch` / `company_scope_mismatch` | Body company ≠ header/key company |
| 404 | `company_not_found` / export not found | Unknown id |

Per-row ingest errors appear in `errors[]` (e.g. `employee_id_required`, `worker_not_found`, `company_id_required`).

---

## 6) What the platform does NOT need from WorkPass Lohn yet

You do **not** need to send us your internal DB schema.  
To go live you only need to implement the calls in §3 (and optionally receive §4).

After you wire it, send us only if different from above:
1. Production Base URL of WorkPass Lohn (for webhook)
2. Exact webhook path if not `/hooks/suppix-hours`
