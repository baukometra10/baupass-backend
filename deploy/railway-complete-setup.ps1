# Full Railway readiness check (run BEFORE setting keys — shows what's missing)
param(
    [string]$BaseUrl = $env:PUBLIC_BASE_URL
)

$ErrorActionPreference = "Continue"
if (-not $BaseUrl) {
    $BaseUrl = Read-Host "Production URL (e.g. https://baupass-production.up.railway.app)"
}
$BaseUrl = $BaseUrl.TrimEnd("/")

Write-Host "`n=== BauPass Railway Complete Setup ===" -ForegroundColor Cyan
Write-Host "URL: $BaseUrl`n"

& "$PSScriptRoot\railway-health-check.ps1" -BaseUrl $BaseUrl

try {
    $setup = Invoke-RestMethod -Uri "$BaseUrl/api/platform/setup-status" -TimeoutSec 30
    Write-Host "`n--- Setup status (from API) ---" -ForegroundColor Cyan
    Write-Host "Score: $($setup.readyScore.percent)%"
    foreach ($m in $setup.readyScore.missing) {
        Write-Host "  [ ] $m" -ForegroundColor Yellow
    }
    if (-not $setup.readyScore.missing.Count) {
        Write-Host "  All recommended variables are set." -ForegroundColor Green
    }
    Write-Host "`nCopy variables from: .env.railway.example"
    Write-Host "Guide: docs/RAILWAY-COMPLETE-AR.md"
}
catch {
    Write-Host "setup-status failed (deploy latest main first): $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`nWorker service: deploy/railway-worker.service.md"
Write-Host "Field test: scripts/field-test.ps1`n" -ForegroundColor Cyan
