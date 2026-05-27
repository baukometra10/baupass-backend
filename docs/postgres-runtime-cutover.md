# PostgreSQL Runtime Cutover (No-Downtime Plan)

## Goal
Move production runtime from SQLite to PostgreSQL with connection pooling and safe rollback.

## What is already implemented
- PostgreSQL pool adapter in `backend/app/database.py`
- Runtime switch: `BAUPASS_PG_RUNTIME=1` wires `get_db()` to PostgreSQL
- SQL compatibility layer: `backend/app/db/pg_compat.py`, `pg_adapter.py`
- Data migration: `backend/ops/sqlite_to_postgres.py`
- Preflight: `backend/ops/postgres_preflight.py`
- Arabic guide: `docs/postgres-cutover-steps-AR.md`

## Environment variables
- DATABASE_URL=postgresql://user:pass@host:5432/dbname
- BAUPASS_PG_RUNTIME=1
- BAUPASS_ALLOW_SQLITE_PRODUCTION=1
- DB_POOL_MIN_SIZE=2
- DB_POOL_MAX_SIZE=20
- DB_POOL_TIMEOUT_SECONDS=10
- BAUPASS_ENV=production
- BAUPASS_AUDIT_SIGNING_KEY=<32+ chars>
- BAUPASS_SECRET_KEY=<32+ chars>

## Cutover steps
1. Provision PostgreSQL with TLS enabled.
2. Run preflight:
   - python backend/ops/postgres_preflight.py
3. Start app in staging with production config + DATABASE_URL.
4. Verify:
   - /api/health returns checks.database.backend = postgres
   - /api/health/ready = 200
5. Shadow traffic / smoke tests.
6. Production switch.
7. Monitor DB pool stats and error rates for 24h.

## Rollback
1. Keep BAUPASS_ALLOW_SQLITE_PRODUCTION=1 ready for emergency fallback.
2. Remove/disable DATABASE_URL only for emergency.
3. Investigate and fix postgres issue, then re-enable DATABASE_URL.

## Notes
- Current migration runner is SQLite-oriented; keep schema parity controlled during transition.
- New code should use postgres_transaction()/postgres_connection() for PostgreSQL-backed paths.
- Queue runtime now exposes dead-letter stats via /api/health and /api/health/queues.
