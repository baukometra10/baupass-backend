# Railway SQLite login fix — verify Volume + env vars, then health.
param(
    [string]$BaseUrl = "https://suppix-workpass-ai.up.railway.app"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$BaseUrl = $BaseUrl.TrimEnd("/")

Write-Host "`n=== Railway SQLite Login Check ===" -ForegroundColor Cyan
Write-Host "URL: $BaseUrl`n"

& (Join-Path $PSScriptRoot "railway-health-check.ps1") -BaseUrl $BaseUrl

Write-Host "`n--- Manual steps (Railway Dashboard) ---" -ForegroundColor Cyan
Write-Host "1. Service (web) -> Settings -> Volumes -> Add Volume -> Mount path: /data"
Write-Host "2. Variables:"
Write-Host "     BAUPASS_PG_RUNTIME=0"
Write-Host "     BAUPASS_DB_PATH=/data/baupass.db"
Write-Host "     BAUPASS_SECRET_KEY=<min 32 chars>"
Write-Host "     PUBLIC_BASE_URL=$BaseUrl"
Write-Host "3. Deploy -> Redeploy"
Write-Host "4. Logs: search for [baupass] init_db"
Write-Host "5. Re-run: powershell -File .\deploy\railway-sqlite-verify.ps1 -BaseUrl $BaseUrl"
Write-Host ""
