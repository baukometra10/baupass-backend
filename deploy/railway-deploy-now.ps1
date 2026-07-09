# One-shot: Railway login (if needed) -> link -> deploy -> health check
# Run in an INTERACTIVE terminal (Cursor Terminal or PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\deploy\railway-deploy-now.ps1
param(
    [string]$BaseUrl = "https://suppix-workpass-ai.up.railway.app",
    [string]$ServiceId = $env:RAILWAY_SERVICE_ID,
    [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$BaseUrl = $BaseUrl.TrimEnd("/")

Write-Host ""
Write-Host "=== BauPass Railway Deploy ===" -ForegroundColor Cyan
Write-Host "Target: $BaseUrl"
Write-Host "Source: $Root"
Write-Host ""

if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Railway CLI..." -ForegroundColor Yellow
    npm install -g @railway/cli@latest
}

# --- Auth ---
$who = railway whoami 2>&1 | Out-String
if ($who -match "Unauthorized|Please login") {
    Write-Host "Not logged in. Opening browser for Railway login..." -ForegroundColor Yellow
    Write-Host "(Alternative: set `$env:RAILWAY_API_TOKEN from https://railway.com/account/tokens )" -ForegroundColor DarkGray
    railway login
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Login failed or cancelled." -ForegroundColor Red
        exit 1
    }
    $who = (railway whoami 2>&1 | Out-String).Trim()
}
Write-Host "Logged in: $($who.Trim())" -ForegroundColor Green

# --- Link project ---
if (-not (Test-Path (Join-Path $Root ".railway"))) {
    Write-Host ""
    Write-Host "Link project (select: baupass-production -> service web):" -ForegroundColor Yellow
    railway link
    if ($LASTEXITCODE -ne 0) {
        Write-Host "railway link failed." -ForegroundColor Red
        exit 1
    }
}
else {
    Write-Host "Project linked (.railway exists)." -ForegroundColor Green
}

# --- Required variables reminder ---
Write-Host ""
Write-Host "Required Railway variables (Service -> Variables):" -ForegroundColor Cyan
Write-Host "  BAUPASS_PG_RUNTIME=0"
Write-Host "  BAUPASS_DB_PATH=/data/baupass.db"
Write-Host "  BAUPASS_SECRET_KEY=<min 32 chars>"
Write-Host "  PUBLIC_BASE_URL=$BaseUrl"
Write-Host "  Volume mount: /data"
Write-Host ""
Write-Host "Current variables (names only):" -ForegroundColor DarkGray
railway variables 2>&1 | Select-Object -First 25

if ($SkipDeploy) {
    Write-Host "SkipDeploy set — no upload." -ForegroundColor Yellow
    exit 0
}

# --- Deploy ---
Write-Host ""
Write-Host "Uploading and deploying (2-5 min)..." -ForegroundColor Cyan
if (Test-Path "$Root\scripts\sync-signotec-vendor.js") {
    node "$Root\scripts\sync-signotec-vendor.js" 2>$null
}
if ($ServiceId) {
    railway up --service $ServiceId --detach
}
else {
    railway up --detach
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "railway up failed." -ForegroundColor Red
    exit 1
}

Write-Host "Waiting 90s for container start..." -ForegroundColor Yellow
Start-Sleep -Seconds 90

& (Join-Path $PSScriptRoot "railway-health-check.ps1") -BaseUrl $BaseUrl
Write-Host ""
Write-Host "Logs: railway logs --lines 80" -ForegroundColor Cyan
Write-Host "Done." -ForegroundColor Green
