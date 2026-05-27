# PostgreSQL Cutover Runbook

**Do not enable `BAUPASS_PG_RUNTIME=1` until this completes.**

## 1. Backup SQLite

```bash
cp /data/baupass.db /data/baupass.db.bak-$(date +%Y%m%d)
```

## 2. Migrate data

```bash
export DATABASE_URL=postgresql://user:pass@host:5432/railway
python backend/ops/sqlite_to_postgres.py --sqlite /data/baupass.db
```

Optional: `--truncate` on empty PG only.

## 3. Bootstrap schema

Ensure `BAUPASS_PG_AUTO_BOOTSTRAP=1` or run migrations on PG.

## 4. Switch runtime

On Railway API service:

```env
BAUPASS_PG_RUNTIME=1
DATABASE_URL=postgresql://...
BAUPASS_ALLOW_SQLITE_PRODUCTION=0
```

Remove conflicting SQLite-only paths after verification.

## 5. Verify

```bash
curl https://SERVICE/api/health/ready
curl https://SERVICE/api/platform/database-status  # superadmin
```

## Rollback

Set `BAUPASS_PG_RUNTIME=0`, keep `/data/baupass.db` volume.
