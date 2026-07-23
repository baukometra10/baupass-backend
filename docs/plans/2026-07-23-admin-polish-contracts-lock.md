# Admin Polish + Contracts Owner Lock

## Goal
Polish `admin-v2` for a clean, fast, cohesive admin experience, and protect employment contracts (salary data) so only someone with a company-owner PIN can open them — without breaking normal `company-admin` access to the rest of the system.

## Recommended approach (contracts)
Do **not** invent a new global `owner` role.

Add a **company-scoped contracts PIN** (step-up unlock):
- Stored as `companies.contract_pin_hash` (+ set-by / updated-at).
- Session unlock: `sessions.contracts_unlocked_until` + `sessions.contracts_unlocked_company_id`.
- TTL default: 15 minutes (`BAUPASS_CONTRACTS_UNLOCK_TTL_MINUTES`).
- Rate-limit wrong attempts (5 / 5 min), same pattern as worker badge PIN.
- **Backward compatible:** if no PIN is set yet, contracts stay open; show a nudge to set a PIN.
- Apply lock to all authenticated admin contract APIs; leave public sign + worker-app own contracts unchanged.

Who sets the PIN: company-admin (owner) on first use; rotate with current PIN or unlocked session; superadmin can force-reset with distinct audit event.

## Phases

### Phase 1 — Security + contracts UI (first PR)
- New: `backend/app/platform/security/contracts_lock.py`
- Columns on `companies` + `sessions` in `backend/server.py`
- Endpoints in `backend/app/domains/contracts/routes.py`:
  - `GET /api/contracts/lock-status`
  - `POST /api/contracts/unlock`
  - `POST /api/contracts/lock`
  - `POST /api/contracts/pin`
- Decorate salary-bearing contract handlers with `@require_contracts_unlocked`
- `admin-v2/contracts.html`: unlock overlay + first-run set-PIN + lock badge; visual polish of the contracts page within existing tokens
- `admin-v2/app.js`: Betrieb/Operations contract cards show locked state when PIN required
- Tests: `backend/tests/test_contracts_lock.py`

### Phase 2 — Shell visual cohesion
- Shared `.empty-state` + consistent skeletons across tabs
- Normalize section headers / card language in `admin-v2/styles.css` + `app.js`
- Tighten overview, workers, access, inbox visual hierarchy (no redesign, reuse tokens)

### Phase 3 — Integrations / invoices / messaging
- Unify integration status cards (tools wizard + platform AI/FCM/wallet)
- Add read-only billing summary in admin-v2 linking to legacy invoices UI (no full invoice migration yet)
- Polish inbox/chat empty states and status badges

### Phase 4 — Performance
- Extend per-tab cache pattern (like ops overview cache)
- Split heavy contracts inline script where useful
- Index checks for contracts list hot paths

## Visual rules
- Keep existing CSS variables (`--bg`, `--accent`, `--panel`, `--radius`, …)
- Reuse `.betrieb-action-locked` language for PIN-locked cards
- Support `theme-black` / `theme-white` and RTL (`ar`)
- No purple/gradient AI aesthetic; no new build toolchain

## Explicitly deferred
- Full invoices CRUD migration into admin-v2
- Field-level salary redaction (v1 = all-or-nothing lock)
- Generalized step-up auth framework for all domains
- Changing public signing or worker self-view of own contract

## Test plan (Phase 1)
- No PIN → contracts still work
- Set PIN → locked until unlock
- Wrong PIN ×5 → lockout
- Unlock → access for TTL; manual lock works
- Superadmin unlock scoped to selected company
- Public sign + worker-app contracts unaffected
- Existing `test_contracts_and_chat_routes.py` still passes

## Decision
Approved: SMS OTP to owner phone + email backup (Phase 1 implemented).

## Status
- Phase 1 (contracts OTP lock + contracts UI gate): DONE
- Phase 2 (shell cohesion / empty states): DONE
- Phase 3 (billing summary + inbox/chat polish): DONE
- Phase 4 (light caches): DONE
- Hardening follow-up (2026-07-23):
  - Durable hashed OTP + fail counters in `step_up_otps` / `step_up_fail_counts`
  - Shared owner step-up on worker/access/payroll exports
  - Recent invoices list in admin-v2 billing panel
  - Platform/tools channel readiness (SMS/Stripe/Redis/email/OpenAI)
  - Copilot empty/quota messaging
  - Extra contract list/sign indexes (migration 041)
- Hardening follow-up 2 (2026-07-23):
  - Enforce owner phone setup in production (`BAUPASS_OWNER_STEP_UP_ENFORCE`, default on outside testing)
  - OTP request rate-limit (45s / 8 per hour) + delivery-fail alerts
  - Richer step-up audit events (`step_up.*`)
  - Invoice PDF download from admin-v2 billing panel
  - Contracts page script split to `contracts-app.js`
  - Daily job alerts for down critical channels
- Deferred: full invoices CRUD in admin-v2; field-level salary redaction
