# BauPass - Railway Deploy (ohne GitHub)
# Vorher in DIESEM Terminal:
#   $env:RAILWAY_API_TOKEN = "Ihr Account-Token"
# Dann:
#   powershell -ExecutionPolicy Bypass -File .\deploy\railway-setup.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($env:RAILWAY_TOKEN -and $env:RAILWAY_API_TOKEN) {
    Remove-Item Env:RAILWAY_TOKEN -ErrorAction SilentlyContinue
    Write-Host "Hinweis: Nur RAILWAY_API_TOKEN verwendet (nicht beide gleichzeitig)." -ForegroundColor Yellow
}

function Test-RailwayCli {
    if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
        Write-Host "Installiere Railway CLI..." -ForegroundColor Yellow
        npm install -g @railway/cli
    }
}

function Test-RailwayAuth {
    $who = railway whoami 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or $who -match "Unauthorized|Invalid") {
        return $false
    }
    Write-Host "Angemeldet als: $($who.Trim())" -ForegroundColor Green
    return $true
}

function Start-RailwayLogin {
    Write-Host ""
    Write-Host "=== Anmelden (Browser) ===" -ForegroundColor Cyan
    railway login
}

function Ensure-RailwayLink {
    if (Test-Path (Join-Path $Root ".railway")) {
        Write-Host "Projekt verknuepft (.railway)." -ForegroundColor Green
        return
    }
    Write-Host ""
    Write-Host "=== Projekt waehlen ===" -ForegroundColor Cyan
    Write-Host "Waehlen: Ihr Workspace -> baupass-control -> Service web"
    railway link
    if ($LASTEXITCODE -ne 0) {
        throw "railway link fehlgeschlagen."
    }
}

function Start-RailwayDeploy {
    Write-Host ""
    Write-Host "=== Code hochladen ===" -ForegroundColor Cyan
    railway up --detach
    if ($LASTEXITCODE -ne 0) {
        throw "railway up fehlgeschlagen."
    }
    Write-Host ""
    Write-Host "Deploy gestartet. In 3-8 Min pruefen:" -ForegroundColor Green
    Write-Host "  https://baupass-control.up.railway.app/api/health"
    Write-Host "  https://baupass-control.up.railway.app/worker-build.json"
}

Test-RailwayCli

if (-not $env:RAILWAY_API_TOKEN) {
    Write-Host ""
    Write-Host "FEHLER: Kein RAILWAY_API_TOKEN gesetzt." -ForegroundColor Red
    Write-Host ""
    Write-Host "So holen Sie den richtigen Token:"
    Write-Host "  1. railway.app -> Profil -> Account Settings -> Tokens"
    Write-Host "  2. Create Token (Account Token, nicht OAuth Client ID)"
    Write-Host "  3. Im Terminal:"
    Write-Host '     $env:RAILWAY_API_TOKEN = "IHR_TOKEN"'
    Write-Host "  4. Skript erneut starten"
    Write-Host ""
    Write-Host "Oder: railway login   (ohne Token)"
    exit 1
}

Write-Host "Verwende RAILWAY_API_TOKEN." -ForegroundColor Green

if (-not (Test-RailwayAuth)) {
    Write-Host "Token ungueltig oder abgelaufen." -ForegroundColor Red
    Write-Host "Neuen Token unter Account Settings -> Tokens erstellen."
    exit 1
}

Ensure-RailwayLink
Start-RailwayDeploy
