# Einmal ausfuehren — Browser-Login, Projekt verknuepfen, Status anzeigen
# Im Cursor-Terminal (interaktiv):
#   powershell -ExecutionPolicy Bypass -File .\deploy\railway-login-link.ps1
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host ""
Write-Host "=== BauPass Railway: Login + Link ===" -ForegroundColor Cyan
Write-Host "Production: https://suppix-workpass-ai.up.railway.app"
Write-Host ""

Remove-Item Env:RAILWAY_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:RAILWAY_API_TOKEN -ErrorAction SilentlyContinue
railway logout 2>$null

Write-Host "Schritt 1/3: Browser oeffnet sich — bitte bei railway.app einloggen." -ForegroundColor Yellow
railway login
if ($LASTEXITCODE -ne 0) {
    Write-Host "Login abgebrochen oder fehlgeschlagen." -ForegroundColor Red
    exit 1
}

$who = (railway whoami 2>&1 | Out-String).Trim()
Write-Host "Angemeldet: $who" -ForegroundColor Green

Write-Host ""
Write-Host "Schritt 2/3: Projekt waehlen:" -ForegroundColor Yellow
Write-Host "  Workspace -> baupass-production -> Service web"
railway link
if ($LASTEXITCODE -ne 0) {
    Write-Host "railway link fehlgeschlagen." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Schritt 3/3: Deployments + Logs + Health..." -ForegroundColor Yellow
& (Join-Path $PSScriptRoot "railway-cli-status.ps1")
