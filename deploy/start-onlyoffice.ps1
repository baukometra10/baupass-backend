# Start OnlyOffice Document Server for WorkPass Docs (port 8081)
# Requires Docker Desktop. Usage: .\deploy\start-onlyoffice.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ComposeDir = Join-Path $PSScriptRoot "onlyoffice"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "FEHLER: Docker fehlt. Bitte Docker Desktop installieren." -ForegroundColor Red
    exit 1
}

if (-not $env:ONLYOFFICE_JWT_SECRET) {
    $env:ONLYOFFICE_JWT_SECRET = "workpass-onlyoffice-dev-secret"
}

Write-Host "Starte OnlyOffice Document Server auf http://127.0.0.1:8081 ..." -ForegroundColor Cyan
Set-Location $ComposeDir
docker compose up -d

Write-Host ""
Write-Host "OnlyOffice laeuft (erster Start kann 1-2 Min dauern)." -ForegroundColor Green
Write-Host "  UI:     http://127.0.0.1:8081"
Write-Host "  Secret: $env:ONLYOFFICE_JWT_SECRET"
Write-Host ""
Write-Host "In einer zweiten Shell BauPass starten mit:" -ForegroundColor Yellow
Write-Host '  $env:ONLYOFFICE_ENABLED="1"'
Write-Host '  $env:ONLYOFFICE_URL="http://127.0.0.1:8081"'
Write-Host '  $env:ONLYOFFICE_JWT_SECRET="workpass-onlyoffice-dev-secret"'
Write-Host '  $env:ONLYOFFICE_APP_URL="http://host.docker.internal:8080"'
Write-Host "  .\deploy\start-lokal.ps1"
Write-Host ""
Write-Host "Stoppen: docker compose -f deploy\onlyoffice\docker-compose.yml down" -ForegroundColor Yellow
