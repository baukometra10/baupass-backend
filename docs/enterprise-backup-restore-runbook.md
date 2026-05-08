# Enterprise Backup + Restore Runbook

## Goal

This runbook ensures production backup is not only created but also verified by restore test.

## Scope

- SQLite database backups for BauPass backend
- Automatic retention cleanup
- Restore verification (integrity + required tables)

## Scripts

- Backup tool: backend/ops/db_backup.py
- PowerShell wrapper: scripts/run_backup.ps1
- Restore verification wrapper: scripts/verify_backup_restore.ps1

## Output Location

- Backups: backend/backups/sqlite
- Restore check temp copies: backend/backups/sqlite/restore-check
- Metadata JSON: next to each backup file

## 1) Manual backup

Run from repository root:

```powershell
python backend/ops/db_backup.py backup
```

Or:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_backup.ps1
```

Expected output: JSON with ok=true, backupPath, sha256, rotation info.

## 2) Manual restore verification (required)

Run:

```powershell
python backend/ops/db_backup.py verify-restore
```

Or:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_backup_restore.ps1
```

Expected output: JSON with ok=true, integrityCheck="ok", no missingRequiredTables.

## 3) Retention policy

- Default retention: 30 days
- Configure with env variable:

```powershell
$env:BAUPASS_DB_BACKUP_RETENTION_DAYS = "30"
```

## 4) Daily scheduling (Windows Task Scheduler)

Create backup task (01:30 daily):

```powershell
schtasks /Create /TN "BauPass-DB-Backup" /SC DAILY /ST 01:30 /TR "powershell -ExecutionPolicy Bypass -File C:\Users\u4363\Desktop\baustelle\scripts\run_backup.ps1" /F
```

Create restore verification task (02:00 daily):

```powershell
schtasks /Create /TN "BauPass-DB-Restore-Verify" /SC DAILY /ST 02:00 /TR "powershell -ExecutionPolicy Bypass -File C:\Users\u4363\Desktop\baustelle\scripts\verify_backup_restore.ps1" /F
```

## 5) Release gate (must pass)

Before production release, verify:

1. Latest backup exists and has metadata JSON.
2. Verify-restore command returns ok=true.
3. integrityCheck is "ok".
4. Required core tables exist: users, companies, workers, access_logs.

## 6) Recovery procedure

If production DB fails:

1. Stop backend process.
2. Pick latest healthy backup from backend/backups/sqlite.
3. Replace production DB file with backup copy.
4. Start backend.
5. Validate /api/health and admin login.

## 7) Incident evidence

For each backup/restore run, store the JSON output in operations logs.

Suggested fields to archive:

- createdAt
- backupPath
- sha256
- integrityCheck
- missingRequiredTables
- rowCounts
