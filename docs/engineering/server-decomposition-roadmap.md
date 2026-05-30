# Server.py Decomposition Roadmap

`backend/server.py` (~26k lines) is the main maintenance risk. Goal: **independent domains** with routes → services → repositories.

## Principles

See `backend/app/domains/README.md`:

1. Move **one route group** at a time.
2. **Delegate** to legacy helpers until SQL moves to repositories.
3. Remove `@app.route` only after blueprint tests pass.
4. Register in `backend/app/api/blueprint_registry.py`.

## Priority order (recommended)

| Phase | Domain / module | Routes (examples) | Effort |
|-------|-----------------|-------------------|--------|
| 0 | Already extracted | `platform/*`, `worker_app`, domains scaffold | done |
| 1 | `platform/sector` + `platform/rbac` | `/api/platform/sectors`, `sector-config`, `rbac/catalog` | done |
| 2 | `domains/reporting/` | **8 routes** wired via blueprint; logic still in `server.py` handlers | in progress |
| 3 | `domains/auth/` | login, logout, 2FA, SSO callbacks (thin wrappers) | high |
| 4 | `domains/access/` | gates, visitors, access logs | high |
| 5 | `domains/workers/` | CRUD, documents, leave | very high |
| 6 | `domains/billing/` | invoices, plans, Stripe | high |

## First concrete slice (phase 2)

```
backend/app/domains/reporting/
  routes.py      # Blueprint prefix /api/reporting
  service.py     # email_pdf, incidents_visits, datev
  repository.py  # read-only queries for reports
```

Move from `server.py`:

- `POST /api/reporting/email-pdf`
- `POST /api/reporting/email-incidents-visits-pdf`
- `POST /api/reporting/email-datev-csv`

Keep `require_auth` decorators in routes; call existing `backend.app.platform.reports.*` modules.

## What NOT to do

- Big-bang rewrite of all routes in one PR.
- Duplicate business logic in domain + server.
- New features in `server.py` when a blueprint exists for that area.

## Success metrics

- Lines in `server.py` decrease quarter over quarter.
- New endpoints land in `backend/app/` first.
- Each moved group has ≥1 test in `backend/tests/`.
