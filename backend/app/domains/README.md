# BauPass Domain Modules

`backend/server.py` keeps **handler implementations** during migration; **all HTTP routing** lives in domain blueprints.

## Layout

```
backend/app/domains/
  registry.py       # Canonical registration order (single source of truth)
  __init__.py       # register_domain_blueprints()
  _routes.py        # mount_rules() helper
  shared.py         # company_id_from_user(), forbidden_company()
  http/             # SPA + static (no /api prefix) — registered LAST
  runtime/          # health, system, public, QR
    qr_views.py     # Unified GET /api/qr.png (public + session)
  auth/             # login, sessions, 2FA
  settings/         # global SMTP/IMAP
  rbac/             # legacy roles + audit-trail
  companies/        # tenants, subcompanies, mail-settings
  workers/          # worker CRUD, documents
  onboarding/       # v2 onboarding only
  access/           # gates, access-logs, geofences
  devices/          # device register, scan, heartbeat
  workforce/        # foreman, analytics, sync
  operations/       # incidents, messages, snapshot
  compliance/       # compliance overview
  documents/        # inbox, IMAP
  billing/          # invoices
  reporting/        # PDF/email reports
  notifications/    # worker notifications, system-alerts
  admin/            # admin devices, audit-logs, export/import
```

## Registration order (`registry.py`)

| Category | Domains |
|----------|---------|
| foundation | auth, runtime, settings, rbac |
| tenant | companies, workers, onboarding |
| operations | access, devices, workforce, operations, compliance |
| backoffice | documents, billing, reporting, notifications, admin |
| static | **http** (must be last — catch-all static proxy) |

Also registered via `blueprint_registry.py` (not domains):

- `shift_api` — `/api/shift/*`
- `worker_app` — `/api/worker-app/*`
- `platform/*` — enterprise, AI, inbox v2, SSO, sector, …

## Per-domain pattern

| File | Role |
|------|------|
| `routes.py` | `{name}_core_bp` + optional `{name}_v2_bp`; `mount_rules()` |
| `service.py` | Business logic (extract SQL from server handlers here) |
| `repository.py` | Optional data access |

## Rules

1. **No** `@app.route("/api/...")` in `server.py` — only blueprint `add_url_rule`.
2. Handlers in `server.py` keep `@require_auth` / `@require_roles` until moved into services.
3. One URL → one registrar; duplicates break tests (`test_domains_registry.py`).
4. New domain: add package, `register_*_blueprint`, append to `registry.py`, add tests.

## Status

| Area | Routes | Handler logic |
|------|--------|---------------|
| All `/api/*` business routes | ✅ blueprints | 🟡 mostly `server.py` |
| **companies** — alle `/api/companies/*` Handler | ✅ | ✅ `service.py` + `repository.py` |
| **workers** — CRUD, docs, import/export, HCE, app-access, identity (+ v2) | ✅ | ✅ Kern in `service.py`; QR/Foto/`akte.pdf` noch `server.py` |
| `/api/qr*` | ✅ `runtime/qr_views.py` | ✅ unified |
| HTML/static | ✅ `http/` | 🟡 handlers in `server.py` |
| SSO state | ✅ `platform/auth/sso_state.py` | ✅ |

Next step: move SQL from handlers into domain `service.py` / `repository.py` one bounded context at a time.
