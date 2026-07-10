# Railway Worker Service (RQ)

Background jobs (Dunning, IMAP, Session-Cleanup, AI-Briefing) laufen zuverlässiger in einem **eigenen Worker-Prozess**.

## Setup

1. Railway → **New Service** → gleiches Git-Repo wie API
2. **Start Command:** `python -m backend.app.tasks.worker`
3. **Variables** (Reference oder Copy von API):
   - `REDIS_URL` (Pflicht für RQ)
   - `BAUPASS_DB_PATH=/data/baupass.db` + Volume `/data` (SQLite)
   - oder `DATABASE_URL` + `BAUPASS_PG_RUNTIME=1`
   - `BAUPASS_SECRET_KEY`, `BAUPASS_WORKER_JWT_SECRET`, …
4. Optional Job-Modi auf `rq` setzen:
   - `BAUPASS_DAILY_JOBS_MODE=rq`
   - `BAUPASS_DUNNING_MODE=rq`
   - `BAUPASS_INVOICE_RETRY_MODE=rq`
   - `BAUPASS_WORKER_SESSION_CLEANUP_MODE=rq`

## Verifizierung

```http
GET /api/health
GET /api/platform/setup-status
```

Erwartung:
- `backgroundJobs.workers.active` ≥ 1
- `workerService.checklist` alle `ok: true`

## Ohne Worker

Jobs laufen im API-Prozess (`thread`-Modus) — für Production mit Last **nicht empfohlen**.
