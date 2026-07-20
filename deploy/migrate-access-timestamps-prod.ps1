# Prod: backup + dry-run + apply access_logs timestamp migration (Europe/Berlin naive).
# Runs INSIDE the Railway container via `railway ssh` (not `railway run`, which is local).
# Requires: railway login + linked project + local SSH key (~/.ssh/id_ed25519).
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

# Ensure web service is linked (SQLite volume lives there).
railway link -p capable-consideration -e production -s web | Out-Null

function Invoke-RailwayRemote([string]$RemoteCommand) {
    # railway ssh -- <cmd> runs on the service container (Linux + IANA tzdata).
    railway ssh -- $RemoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw "remote command failed: $RemoteCommand"
    }
}

Write-Host "1) Backup on Railway ($DbPath)..." -ForegroundColor Cyan
Invoke-RailwayRemote "python -m backend.ops.db_backup backup --db-path $DbPath"

if ($DryRun -or -not $Apply) {
    Write-Host "2) Dry-run migration..." -ForegroundColor Cyan
    Invoke-RailwayRemote "python -m backend.ops.migrate_access_log_timestamps --dry-run --db-path $DbPath"
}

if ($Apply) {
    Write-Host "3) APPLY migration (IANA Europe/Berlin on Linux host)..." -ForegroundColor Yellow
    Invoke-RailwayRemote "python -m backend.ops.migrate_access_log_timestamps --apply --db-path $DbPath"
    Write-Host "Done. Spot-check Anwesenheit / Monatsauswertung." -ForegroundColor Green
}
