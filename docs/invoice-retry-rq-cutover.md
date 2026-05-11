# Invoice Retry RQ Cutover

## Goal
Run invoice retry cycle via RQ scheduled task instead of inline server thread.

## Implemented
- New one-shot legacy cycle function in backend/server.py:
  - run_invoice_retry_cycle_once()
- New RQ bridge task:
  - backend/app/tasks/legacy_runtime.py
  - run_invoice_retry_cycle_once_task(reschedule=True)
  - bootstrap_legacy_invoice_retry_scheduler()
- start_background_jobs now supports mode switch:
  - BAUPASS_INVOICE_RETRY_MODE=thread (default)
  - BAUPASS_INVOICE_RETRY_MODE=rq

## How to enable
1. Ensure Redis is reachable.
2. Start RQ worker with scheduler:
   - python -m backend.app.tasks.worker
3. Set env:
   - BAUPASS_INVOICE_RETRY_MODE=rq
4. Restart server process.

## Verification
- /api/health/queues should show scheduled queue activity.
- /api/health should include dead_letter stats.
- Check logs for:
  - "Legacy invoice retry scheduler bootstrapped via RQ"

## Rollback
- Set BAUPASS_INVOICE_RETRY_MODE=thread
- Restart server process

## Notes
- This is a transition bridge that reuses proven legacy retry logic.
- Next step is extracting retry logic fully out of backend/server.py into app/services and app/tasks.
