# Railway Worker Service

Duplicate the main API service in the same Railway project:

| Setting | Value |
|---------|--------|
| Start Command | `python -m backend.app.tasks.worker` |
| Dockerfile | same repo root |
| Variables | Reference `REDIS_URL`, copy `BAUPASS_DB_PATH`, secrets |
| Volume | `/data` (same as API if shared DB) |

Without this service, background jobs run in-process (weaker under load).
