# BauPass lokal starten (Python 3.11 - die alte .venv mit 3.14 ist kaputt)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$venvPython = Join-Path $Root ".venv311\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Richte Python 3.11 ein (einmalig, ca. 1-2 Min)..." -ForegroundColor Cyan
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "FEHLER: 'uv' fehlt. Installieren: https://docs.astral.sh/uv/getting-started/installation/" -ForegroundColor Red
        Write-Host "Oder Python 3.11 von python.org installieren und .venv311 manuell anlegen."
        exit 1
    }
    uv python install 3.11
    uv venv --python 3.11 .venv311
    uv pip install -r backend\requirements.txt --python .venv311\Scripts\python.exe
}

$python = $venvPython

Write-Host "Python: $(& $python --version)" -ForegroundColor Green

$env:HOST = "0.0.0.0"
$env:PORT = "8000"
$env:PUBLIC_BASE_URL = "http://localhost:8000"
$env:BAUPASS_DB_PATH = Join-Path $Root "backend\baupass.db"
$env:FLASK_APP = "backend.server"
$env:FLASK_DEBUG = "1"

Write-Host ""
Write-Host "BauPass laeuft lokal:" -ForegroundColor Green
Write-Host "  Admin:       http://localhost:8000/"
Write-Host "  Mitarbeiter: http://localhost:8000/emp-app.html?worker=1&view=card&v=20260627f"
Write-Host ""
Write-Host "Wichtig: Nur localhost:8000 oeffnen - nicht die Railway-URL im Browser." -ForegroundColor Yellow
Write-Host "Browser-Zoom zuruecksetzen: Strg+0 (Windows) / Cmd+0 (Mac)" -ForegroundColor Yellow
Write-Host "Redis-Warnung ist OK (laeuft ohne Redis lokal)." -ForegroundColor Yellow
Write-Host "Lokaler Dev-Mode mit Auto-Reload aktiv." -ForegroundColor Yellow
Write-Host "Beenden mit Strg+C" -ForegroundColor Yellow
Write-Host ""
& $python -m backend.entrypoint --mode dev
