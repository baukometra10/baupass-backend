# Prod: backup + dry-run + apply access_logs timestamp migration (Europe/Berlin naive).
# Requires: railway login + linked project.
# Usage:
#   .\deploy\migrate-access-timestamps-prod.ps1 -DryRun
#   .\deploy\migrate-access-timestamps-prod.ps1 -Apply

param(
    [switch]$DryRun,
    [switch]$Apply,
    [string]$DbPath = "/data/baupass.db"
)

$ErrorActionPreference = "Stop"

if (-not $DryRun -and -not $Apply) {
    Write-Host "Specify -DryRun and/or -Apply" -ForegroundColor Yellow
    exit 1
}

Write-Host "1) Backup on Railway..." -ForegroundColor Cyan
railway run -- python -m backend.ops.db_backup backup --db-path $DbPath
if ($LASTEXITCODE -ne 0) { throw "backup failed" }

if ($DryRun -or -not $Apply) {
    Write-Host "2) Dry-run migration..." -ForegroundColor Cyan
    railway run -- python -m backend.ops.migrate_access_log_timestamps --dry-run --db-path $DbPath
    if ($LASTEXITCODE -ne 0) { throw "dry-run failed" }
}

if ($Apply) {
    Write-Host "3) APPLY migration (IANA Europe/Berlin required on host)..." -ForegroundColor Yellow
    railway run -- python -m backend.ops.migrate_access_log_timestamps --apply --db-path $DbPath
    if ($LASTEXITCODE -ne 0) { throw "apply failed" }
    Write-Host "Done. Spot-check Anwesenheit / Monatsauswertung." -ForegroundColor Green
}
