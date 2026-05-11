# RQ Staging Activation Checklist

## Goal
Safely activate RQ modes in staging and verify resilience before production rollout.

## Required services
1. Redis running and reachable from app + worker.
2. App process running.
3. At least one RQ worker with scheduler:
   - python -m backend.app.tasks.worker

## Environment switches
- BAUPASS_INVOICE_RETRY_MODE=rq
- BAUPASS_WORKER_SESSION_CLEANUP_MODE=rq
- BAUPASS_DAILY_JOBS_MODE=rq
- Optional:
  - BAUPASS_DAILY_JOBS_SECONDS=86400
  - BAUPASS_RQ_HEARTBEAT_SECONDS=10
   - BAUPASS_RQ_STRICT_MODE=1  (recommended after successful staging validation)

## Verification commands
1. Health overview:
   - GET /api/health
2. Queue-specific:
   - GET /api/health/queues

## Expected checks in /api/health
- checks.redis.status == ok
- checks.queues.status == ok
- checks.workers.status == ok
- checks.workers.active >= 1
- status should stay ok (not degraded)

## Failure signals
- status == degraded while rq modes enabled
- checks.workers.active == 0
- dead_letter.total_events increasing quickly

## Rollback
- Set modes back to thread:
  - BAUPASS_INVOICE_RETRY_MODE=thread
  - BAUPASS_WORKER_SESSION_CLEANUP_MODE=thread
  - BAUPASS_DAILY_JOBS_MODE=thread
- Restart app process

## Strict mode rollout
1. First run with strict mode disabled and monitor for at least 24h.
2. Enable BAUPASS_RQ_STRICT_MODE=1.
3. Re-deploy and confirm startup succeeds.
4. If startup fails, investigate worker/Redis bootstrap immediately (no silent thread fallback in strict mode).

## Next hardening
- Remove remaining thread fallback branches after 24h stable staging run.
