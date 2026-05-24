# BauPass live stellen: Docker bauen + pushen (Railway danach: Redeploy)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker nicht installiert." -ForegroundColor Red
    exit 1
}

docker version 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Desktop ist nicht gestartet." -ForegroundColor Red
    Write-Host "1. Docker Desktop oeffnen und warten bis 'Engine running'"
    Write-Host "2. Dieses Skript erneut ausfuehren"
    exit 1
}

Write-Host "Baue Image baupass/baupass:latest ..." -ForegroundColor Cyan
docker build -t baupass/baupass:latest .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Login + Push ..." -ForegroundColor Cyan
docker push baupass/baupass:latest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Fertig. Jetzt im Browser:" -ForegroundColor Green
Write-Host "  railway.app -> web-production-922fe -> Deploy -> Redeploy"
Write-Host ""
Write-Host "Pruefen:" -ForegroundColor Green
Write-Host "  https://web-production-922fe.up.railway.app/worker-build.json"
Write-Host "  Erwartet: build 20260524a"
