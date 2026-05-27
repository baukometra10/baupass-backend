# BauPass Domain Modules

Clean Architecture layout for splitting `backend/server.py` into bounded contexts.

## Structure

```
domains/
  auth/           # Login, sessions, 2FA, RBAC decorators
  workers/        # Worker CRUD, documents, leave, timesheets
  access/         # Gates, geofences, access logs, visitors
  billing/        # Plans, invoices, dunning, approvals
  notifications/  # Email, push, IMAP, system alerts
  admin/          # v2 dashboard aggregates for admin-v2 SPA
```

Each domain follows:

| Layer | File | Responsibility |
|-------|------|----------------|
| Routes | `routes.py` | Flask blueprint — HTTP only, no SQL |
| Service | `service.py` | Business rules, orchestration |
| Repository | `repository.py` | SQL / data access (extends `BaseRepository`) |

## Migration rules

1. **One route at a time** — move from `server.py` to domain `routes.py`.
2. **Delegate first** — service calls legacy `server.py` helpers until logic is extracted.
3. **No duplicate URLs** — remove the old `@app.route` only after the blueprint route is tested.
4. **Tests required** — add or extend `backend/tests/` for each moved endpoint.
5. **Register in** `backend/app/api/blueprint_registry.py`.

## Example flow

```
POST /api/logout
  → domains/auth/routes.py::logout()
  → domains/auth/service.py::AuthService.logout(token)
  → domains/auth/repository.py::SessionRepository.revoke(token)
```

## Current status

| Domain | Routes in server.py | Extracted |
|--------|---------------------|-----------|
| auth | ~15 | scaffold only |
| workers | ~25 | worker-app shim |
| access | ~20 | none |
| billing | ~18 | none |
| notifications | ~12 | none |
