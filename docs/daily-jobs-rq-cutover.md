# Daily Jobs RQ Cutover

## Goal
Run daily jobs cycle via RQ scheduled task instead of inline server thread.

## Implemented
- New one-shot legacy function in backend/server.py:
  - run_daily_jobs_cycle_once()
- New RQ bridge task in backend/app/tasks/legacy_runtime.py:
  - run_daily_jobs_cycle_once_task(reschedule=True)
  - bootstrap_legacy_daily_jobs_scheduler()
- start_background_jobs mode switch:
  - BAUPASS_DAILY_JOBS_MODE=thread (default)
  - BAUPASS_DAILY_JOBS_MODE=rq

## Optional interval override
- BAUPASS_DAILY_JOBS_SECONDS=86400 (default)

## How to enable
1. Ensure Redis is reachable.
2. Start RQ worker with scheduler:
   - python -m backend.app.tasks.worker
3. Set env:
   - BAUPASS_DAILY_JOBS_MODE=rq
4. Restart server process.

## Verification
- /api/health/queues shows scheduled queue activity.
- Logs include:
  - "Legacy daily jobs scheduler bootstrapped via RQ"

## Rollback
- Set BAUPASS_DAILY_JOBS_MODE=thread
- Restart server process

## Strict mode
- Optional hardening: BAUPASS_RQ_STRICT_MODE=1
- In strict mode, bootstrap failures do not fall back to inline thread.

## Notes
- Transition bridge reuses proven legacy daily-job logic.
- Next phase extracts daily-job logic fully out of backend/server.py.
