# Deploy BauPass to Railway without GitHub (Railway CLI uploads local folder).
# Prerequisites: npm install -g @railway/cli && railway login && railway link
param(
    [string]$ServiceId = $env:RAILWAY_SERVICE_ID
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Write-Host "Railway CLI fehlt. Installieren: npm install -g @railway/cli" -ForegroundColor Yellow
    exit 1
}

Write-Host "Deploy from: $Root" -ForegroundColor Cyan

Write-Host "Signotec vendor sync..." -ForegroundColor Cyan
node "$Root\scripts\sync-signotec-vendor.js"
if (Test-Path "$Root\vendor\signotec\STPadServerLib.js") {
    Write-Host "  STPadServerLib.js ready for deploy." -ForegroundColor Green
} else {
    Write-Host "  STPadServerLib.js not found locally — set BAUPASS_SIGNOTEC_LIB_BASE64 on Railway if needed." -ForegroundColor Yellow
}

if ($ServiceId) {
    railway up --service $ServiceId --detach
} else {
    railway up --detach
}

Write-Host ""
Write-Host "Warten Sie 2-5 Minuten, dann pruefen:" -ForegroundColor Green
Write-Host "  https://baupass-production.up.railway.app/worker-build.json"
Write-Host "  https://baupass-production.up.railway.app/api/health"
