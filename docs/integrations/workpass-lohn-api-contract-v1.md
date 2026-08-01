# WorkPass Lohn ↔ SUPPIX Platform — API Contract (v1)

**Base URL (production):** `https://suppix-ai-workpass.com`  
**Product:** WorkPass Lohn (standalone) ↔ WorkPass / SUPPIX platform  
**Auth model:** per-company API key + mandatory company header (tenant lock)

Give this document to the accounting app.

**Normal ops:** connect platform ↔ WorkPass Lohn **once** (`platform-link`).  
Per company, WorkPass Lohn stays **optional** (default OFF). Enable in company Settings UI, on create checkbox, or via `company-settings` API.

---

## 0) One-time setup (platform ↔ WorkPass Lohn) — once only

Superadmin connects the platform to WorkPass Lohn **once**. After that, companies that **opt in** can be provisioned into WorkPass Lohn (Firma-ID + bridge credentials).

```http
POST /api/payroll/accounting/platform-link
Authorization: Bearer <superadmin-session>
Content-Type: application/json

{
  "enabled": true,
  "autoProvision": true,
  "baseUrl": "https://<WORKPASS-LOHN-HOST>",
  "masterApiKey": "<shared-master-key>",
  "companyUpsertPath": "/v1/company/upsert",
  "hoursWebhookPath": "/hooks/suppix-hours",
  "platformPublicUrl": "https://suppix-ai-workpass.com",
  "runDay": 1
}
```

**UI tools (superadmin):**
- Legacy: Admin → Einstellungen → **WorkPass Lohn — Buchhaltungs-App verbinden**
- Admin-v2: Tab **Plattform** → panel **WorkPass Lohn — Plattform-Link**
- Ops Command Center shows link status
- CLI: `.\deploy\link-workpass-lohn.ps1 -BaseUrl https://lohn… -MasterKey … -PlatformUrl https://suppix-ai-workpass.com`

Connectivity check:

```http
POST /api/payroll/accounting/platform-link/test
```

Env alternative:

```text
SUPPIX_WORKPASS_LOHN_ENABLED=1
SUPPIX_WORKPASS_LOHN_BASE_URL=https://<WORKPASS-LOHN-HOST>
SUPPIX_WORKPASS_LOHN_MASTER_KEY=<shared-master-key>
SUPPIX_PUBLIC_BASE_URL=https://suppix-ai-workpass.com
```

What happens on `POST /api/companies` (create company):
- If platform-link is **enabled** and **autoProvision=true**: WorkPass Lohn is **auto-enabled** and the new company-admin **username + password** are pushed to Lohn via:
  1. `POST /v1/company/upsert` (`access` / `login` fields)
  2. `POST /v1/company/login-sync` (required by Lohn UI — without this, Lohn shows “kein Passwort”)
- Explicit `"workpassLohnEnabled": false` keeps Lohn off.
- Explicit `"workpassLohnEnabled": true` (or the admin UI checkbox) also provisions + pushes credentials.
- Re-enabling an older company without a stored plaintext password **mints a temporary admin password**, updates the company-admin hash, and sends it via `login-sync` (returned once as `temporaryAdminPassword`).
- Later toggle anytime in **company card → Settings / Einstellungen**, or:

```http
PUT /api/payroll/accounting/company-settings
{ "companyId": "<FIRMA-ID>", "workpassLohnEnabled": false }
```

WorkPass Lohn can also **pull** credentials anytime:

```http
GET /api/v2/accounting/company/access
X-WorkPass-Company-Id: <FIRMA-ID>
X-Accounting-Key: acc_live_…
```

Response:

```json
{
  "ok": true,
  "companyId": "<FIRMA-ID>",
  "access": {
    "username": "firmaadmin",
    "password": "…",
    "role": "company-admin",
    "firmaId": "<FIRMA-ID>",
    "companyId": "<FIRMA-ID>"
  },
  "login": { "username": "firmaadmin", "password": "…" }
}
```

On company-admin password reset, credentials are re-pushed to Lohn automatically (when Lohn is enabled).

Payslips flow (already live):
1. Lohn → `POST /api/v2/accounting/statements` (PDF batch)
2. Platform status `pending_approval`
3. Human approves → `lohnabrechnung` document + push to employee

Company legal texts (Impressum / Datenschutz):

```http
PUT /api/companies/<company_id>/legal
{ "impressumText": "...", "datenschutzText": "..." }
```

Ops Command Center shows platform-link status for superadmin.

When disabled: platform **stops all outbound** hours/webhooks for that company (`403 workpass_lohn_disabled` on bridge).

Backfill existing companies:

```http
POST /api/payroll/accounting/provision-all
Authorization: Bearer <superadmin-session>
{ "force": false }
```

Manual (optional) per-company key rotate remains available via `POST /api/payroll/accounting/integration` — not required for normal onboarding.

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

### 3.0 Pull employee master (full Stammdaten)

```http
GET /api/v2/accounting/employees
X-WorkPass-Company-Id: <FIRMA-ID>
X-Accounting-Key: acc_live_…
```

Returns `format: platform.employees.v1` with every active worker and payroll fields:
`iban`, `taxId`, `insuranceNumber`, `birthDate`, `email`, `phone`, `address`, `nationality`,
`gender`, `jobTitle`, `hourlyRate`, `salaryGrossMonthly`, `missingFields`, `payrollReady`.

### 3.1 Pull monthly hours (+ master on each row)

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
  "includesMasterData": true,
  "payrollReadyCount": 1,
  "incompleteCount": 0,
  "rows": [
    {
      "employeeId": "w1",
      "hours": 160,
      "hourlyRate": 15,
      "iban": "DE…",
      "taxId": "…",
      "missingFields": [],
      "payrollReady": true
    }
  ]
}
```

Each hours / payroll-batch employee row includes the **same master fields** as `/employees`
so Lohn never needs a second round-trip for IBAN/Steuer-ID when pulling Abrechnung inputs.

Notes:
- `grossEstimate` is a **hint only** — WorkPass Lohn computes official payroll.
- `employeeId` / `workerId` = platform worker UUID/id (use this in `storageKey`, not the display name).

### 3.1b Pull payroll batch (`platform.payroll.batch.v1`)

Preferred for monthly Lohn jobs. Same tenant auth as hours.

```http
GET /api/v2/accounting/payroll-batch?period=2026-07
X-WorkPass-Company-Id: <FIRMA-ID>
X-Accounting-Key: acc_live_…
```

Or POST body:

```http
POST /api/v2/accounting/payroll-batch
X-WorkPass-Company-Id: <FIRMA-ID>
X-Accounting-Key: acc_live_…

{ "companyId": "<FIRMA-ID>", "period": "2026-07" }
```

Response includes `format` / `capability` = `platform.payroll.batch.v1`, plus `employees[]` and `rows[]`.

### 3.1c Platform push → Lohn (when pull URL is not configured)

Platform also sends the same payload outbound:

```http
POST {LOHN_BASE}/v1/payroll/batch
X-WorkPass-Key: <MASTER-KEY>
X-WorkPass-Company-Id: <FIRMA-ID>

{ "format": "platform.payroll.batch.v1", "companyId": "…", "period": "2026-07", "employees": [ … ] }
```

Triggered by monthly job / `POST /api/payroll/accounting/export-now` / `POST /api/payroll/accounting/push-payroll-batch`.  
After a successful push, Lohn only needs «Nur Freigabe offener Jobs».

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

### 3.2b Missing employee data (Steuer / Lohn → Platform)

When payroll cannot complete because employee master data is incomplete, Lohn/Steuer notifies the platform. Admins see the notice in Ops Command Center and dismiss it with **Gelesen / ausblenden**.

```http
POST /api/v2/accounting/employee-data-alerts
X-WorkPass-Company-Id: <FIRMA-ID>
X-Accounting-Key: acc_live_…

{
  "companyId": "<FIRMA-ID>",
  "period": "2026-07",
  "issues": [
    {
      "employeeId": "w-1001",
      "workerId": "w-1001",
      "missingFields": ["taxId", "iban", "birthDate"],
      "message": "Steuer-ID und IBAN fehlen"
    }
  ]
}
```

Admin list / dismiss:

```http
GET  /api/payroll/accounting/data-alerts
POST /api/payroll/accounting/data-alerts/<alertId>/dismiss
```

### 3.2c Accounting message inbox (`accounting.message`)

Lohn configures:

```text
WORKPASS_PLATFORM_WEBHOOK_URL=https://suppix-ai-workpass.com/api/v2/accounting/webhook
```

**Inbound webhook (Lohn → Platform):**

```http
POST /api/v2/accounting/webhook
X-WorkPass-Key: <MASTER-KEY>
X-WorkPass-Company-Id: <FIRMA-ID>
X-Suppix-Event: accounting.message

{
  "event": "accounting.message",
  "companyId": "<FIRMA-ID>",
  "id": "msg-42",
  "kind": "missing_data",
  "subject": "Fehlende Mitarbeiterdaten",
  "body": "Steuer-ID fehlt für Ali Hassan",
  "period": "2026-07",
  "workerId": "w-1001"
}
```

On receive, the platform stores the message and also pulls:

```http
GET {LOHN}/v1/messages/pending?companyId=<FIRMA-ID>
```

**Admin inbox (Ops Command Center):**

```http
GET  /api/payroll/accounting/messages
POST /api/payroll/accounting/messages/sync
POST /api/payroll/accounting/messages/<id>/open
```

Opening / clicking a message marks it read and acks Lohn:

```http
POST {LOHN}/v1/messages/ack
{ "messageId": "msg-42", "companyId": "<FIRMA-ID>" }
```

After ack the message leaves the platform inbox.

### Live-Test (ohne Lohn)

Superadmin in Ops Command Center:

1. Firma wählen (`?company_id=…`) oder erste Firma in der Liste
2. Button **Testnachricht**
3. Gelbe Mitteilung oben prüfen
4. **Mitteilung weg** → Banner weg, Posteingang bleibt ungelesen
5. **Öffnen & bestätigen** → Nachricht verschwindet

API:

```http
POST /api/payroll/accounting/messages/test
{ "companyId": "<FIRMA-ID>", "period": "2026-07", "kind": "missing_data" }
```

### 3.3 Push payslip batch (PDF)

```http
POST /api/v2/accounting/statements
```

### 3.3b Pull Abrechnung status

```http
GET /api/v2/accounting/statements?period=2026-06
X-WorkPass-Company-Id: <FIRMA-ID>
X-Accounting-Key: acc_live_…
```

Returns `format: platform.statements.status.v1` with batches (`pending_approval` / approved / rejected)
and per-statement release flags. Approval stays human on the platform — never auto-approve.

Body for POST:

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
