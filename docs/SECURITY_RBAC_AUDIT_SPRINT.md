# Security & RBAC Audit Sprint (Backend)

## Goal
Ship a fast, verifiable security hardening pass for authentication, authorization (RBAC), and tenant isolation without breaking current flows.

## Scope (Week 1)
- API auth consistency (401/403 behavior)
- Role checks (superadmin/company-admin/turnstile/worker)
- Tenant boundary enforcement (company_id isolation)
- Security regression tests for sensitive endpoints
- Audit-log coverage for high-risk actions

## Hotspots discovered in current codebase
- `backend/server.py` (global auth helpers and many routes)
- `backend/app/domains/workers/service.py`
  - role checks and forbidden responses are present but should be centralized and tested by matrix
- `backend/app/middleware/security.py`
  - authorization + CSRF related controls
- `backend/app/middleware/tenant.py`
  - tenant context and boundary assumptions
- `backend/app/platform/api_platform/routes.py`
  - mixed API-key + user-role paths
- `backend/app/api/openapi_spec.py`
  - documented role requirements, needs parity check against actual route guards

## RBAC matrix to enforce
- **superadmin**: cross-company access where explicitly intended
- **company-admin**: only own `company_id`
- **turnstile**: limited operational endpoints only
- **worker**: worker-app endpoints only; no admin routes
- **anonymous**: 401 everywhere except explicit public endpoints

## Checklist (execution order)

### 1) Route guard inventory
- Build a table: route, method, required auth, required role(s), tenant restriction.
- Compare:
  - implementation guards
  - OpenAPI declared roles
  - expected product behavior

**Done when:** no undocumented privileged route remains.

### 2) 401/403 normalization
- Ensure unauthenticated => 401, unauthorized => 403 across all sensitive endpoints.
- Remove ambiguous error variants where possible.

**Done when:** tests assert consistent status code contract.

### 3) Tenant isolation verification
- For all company-scoped reads/writes:
  - enforce `company_id` match in query/service layer
  - superadmin exceptions are explicit and tested

**Done when:** cross-tenant access tests fail by design (403/404 policy).

### 4) Sensitive action audit logging
- Verify audit log entries exist for:
  - worker create/update/delete/lock
  - role/security setting changes
  - camera/watch escalation operations

**Done when:** each sensitive action produces traceable audit record.

### 5) Regression test pack
Create/expand tests for:
- Auth missing token => 401
- Wrong role => 403
- Cross-company attempt => 403
- Correct role + same company => 200/201

Target tests under `backend/tests/` (new files allowed):
- `test_rbac_access_matrix.py`
- `test_tenant_boundary_enforcement.py`
- `test_auth_status_code_contract.py`

**Done when:** tests pass locally and in CI.

## Quick wins (this sprint)
1. Centralize repeated role checks to one helper to reduce drift.
2. Add a failing test first for one known high-risk route group, then fix.
3. Add one smoke command in CI: run only security suite on PR.

## Suggested implementation slices
- **Slice A (Day 1):** inventory + failing tests for auth contract
- **Slice B (Day 2):** tenant boundary tests + fixes in workers domain
- **Slice C (Day 3):** platform API role parity + OpenAPI parity check
- **Slice D (Day 4):** audit log coverage + cleanup
- **Slice E (Day 5):** final security regression run + sign-off report

## Sign-off criteria
- No unauthorized cross-tenant read/write in tested routes
- 401/403 behavior consistent and documented
- RBAC matrix tests green
- Sensitive events auditable
