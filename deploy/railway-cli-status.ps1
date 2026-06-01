# BauPass — Railway CLI: login check, link, deployments, logs
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\deploy\railway-cli-status.ps1
# With token (non-interactive):
#   $env:RAILWAY_API_TOKEN = "..."
#   powershell -ExecutionPolicy Bypass -File .\deploy\railway-cli-status.ps1
param(
    [string]$ProductionUrl = "https://baupass-production.up.railway.app",
    [switch]$SkipHealth
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($env:RAILWAY_TOKEN -and $env:RAILWAY_API_TOKEN) {
    Remove-Item Env:RAILWAY_TOKEN -ErrorAction SilentlyContinue
    Write-Host "Hinweis: Nur RAILWAY_API_TOKEN verwendet." -ForegroundColor Yellow
}

if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Write-Host "Railway CLI fehlt. Installiere: npm install -g @railway/cli" -ForegroundColor Yellow
    exit 1
}

function Show-LoginHelp {
    Write-Host ""
    Write-Host "=== Railway nicht angemeldet ===" -ForegroundColor Red
    Write-Host ""
    Write-Host "Option A - Browser (empfohlen, in DIESEM Terminal):" -ForegroundColor Cyan
    Write-Host "  cd $Root"
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\deploy\fix-railway-login.ps1"
    Write-Host "  railway link    # Workspace -> baupass-production -> Service web"
    Write-Host ""
    Write-Host "Option B - Account Token:" -ForegroundColor Cyan
    Write-Host "  https://railway.com/account/tokens"
    Write-Host '  $env:RAILWAY_API_TOKEN = "IHR_ACCOUNT_TOKEN"'
    Write-Host "  railway whoami"
    Write-Host "  railway link"
    Write-Host ""
    Write-Host "Production URL: $ProductionUrl"
    exit 1
}

$whoOut = railway whoami 2>&1
$who = $whoOut | Out-String
$whoExit = $LASTEXITCODE
if ($whoExit -ne 0 -or $who -match "Unauthorized|Invalid") {
    Show-LoginHelp
}
Write-Host "Angemeldet: $($who.Trim())" -ForegroundColor Green

if (-not (Test-Path (Join-Path $Root ".railway"))) {
    Write-Host ""
    Write-Host "Projekt noch nicht verknuepft. Starte: railway link" -ForegroundColor Yellow
    Write-Host "Waehlen: Workspace -> baupass-production -> Service web"
    railway link
    if ($LASTEXITCODE -ne 0) {
        Write-Host "railway link fehlgeschlagen." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Projekt verknuepft (.railway vorhanden)." -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Letzte Deployments ===" -ForegroundColor Cyan
railway deployment list 2>&1

Write-Host ""
Write-Host "=== Letzte Logs - 50 Zeilen ===" -ForegroundColor Cyan
railway logs --lines 50 2>&1

if (-not $SkipHealth) {
    Write-Host ""
    Write-Host "=== Production Deploy + Health ===" -ForegroundColor Cyan
    $env:PUBLIC_BASE_URL = $ProductionUrl
    & (Join-Path $PSScriptRoot "verify-production-deploy.ps1") -BaseUrl $ProductionUrl
}

Write-Host ""
Write-Host "Fertig. Dashboard: https://railway.com" -ForegroundColor Green
