# Worker Session Cleanup RQ Cutover

## Goal
Run worker-session cleanup cycle via RQ scheduled task instead of inline server thread.

## Implemented
- New one-shot legacy cleanup function in backend/server.py:
  - run_worker_session_cleanup_cycle_once()
- New RQ bridge task in backend/app/tasks/legacy_runtime.py:
  - run_worker_session_cleanup_cycle_once_task(reschedule=True)
  - bootstrap_legacy_worker_session_cleanup_scheduler()
- start_background_jobs mode switch:
  - BAUPASS_WORKER_SESSION_CLEANUP_MODE=thread (default)
  - BAUPASS_WORKER_SESSION_CLEANUP_MODE=rq

## How to enable
1. Ensure Redis is reachable.
2. Start RQ worker with scheduler:
   - python -m backend.app.tasks.worker
3. Set env:
   - BAUPASS_WORKER_SESSION_CLEANUP_MODE=rq
4. Restart server process.

## Verification
- /api/health/queues shows scheduled queue activity.
- Logs include:
  - "Legacy worker session cleanup scheduler bootstrapped via RQ"

## Rollback
- Set BAUPASS_WORKER_SESSION_CLEANUP_MODE=thread
- Restart server process

## Notes
- This is a transition bridge reusing proven cleanup logic.
- Next phase extracts cleanup logic completely out of backend/server.py.
