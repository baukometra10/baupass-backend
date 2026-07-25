# BauPass lokal starten — Port 8080, ohne Background-Jobs (SMTP/IMAP-Spam)
# Usage: .\deploy\start-lokal.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Resolve-LocalPython {
    $candidates = @(
        (Join-Path $Root ".venv-ci\Scripts\python.exe"),
        (Join-Path $Root ".venv311\Scripts\python.exe"),
        (Join-Path $Root ".venv\Scripts\python.exe")
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$python = Resolve-LocalPython
if (-not $python) {
    Write-Host "Kein venv gefunden. Richte Python 3.11 ein..." -ForegroundColor Cyan
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "FEHLER: 'uv' fehlt oder lege .venv-ci manuell an." -ForegroundColor Red
        exit 1
    }
    uv python install 3.11
    uv venv --python 3.11 .venv311
    uv pip install -r backend\requirements.txt --python .venv311\Scripts\python.exe
    $python = Join-Path $Root ".venv311\Scripts\python.exe"
}

Write-Host "Python: $(& $python --version) ($python)" -ForegroundColor Green

# Einheitlich mit Docs und CSRF: immer 8080
$env:HOST = "0.0.0.0"
$env:PORT = "8080"
$env:PUBLIC_BASE_URL = "http://127.0.0.1:8080"
$env:BAUPASS_ENV = "development"
$env:BAUPASS_ENABLE_BACKGROUND_JOBS = "0"
$env:BAUPASS_ENABLE_IMAP_POLLER = "0"
$env:BAUPASS_SKIP_IMAP_POLL = "1"
$env:BAUPASS_DB_PATH = Join-Path $Root "backend\baupass.db"
$env:FLASK_APP = "backend.server"
$env:FLASK_DEBUG = "1"
# AI Operator FAB: voice + once-per-day welcome greeting for company admins
if (-not $env:BAUPASS_AI_OPERATOR_FAB) { $env:BAUPASS_AI_OPERATOR_FAB = "1" }
if (-not $env:BAUPASS_AI_OPERATOR_VOICE) { $env:BAUPASS_AI_OPERATOR_VOICE = "1" }
if (-not $env:BAUPASS_AI_OPERATOR_WELCOME) { $env:BAUPASS_AI_OPERATOR_WELCOME = "1" }

# OnlyOffice (optional — start via .\deploy\start-onlyoffice.ps1)
if (-not $env:ONLYOFFICE_URL) { $env:ONLYOFFICE_URL = "http://127.0.0.1:8081" }
if (-not $env:ONLYOFFICE_JWT_SECRET) { $env:ONLYOFFICE_JWT_SECRET = "workpass-onlyoffice-dev-secret" }
if (-not $env:ONLYOFFICE_APP_URL) { $env:ONLYOFFICE_APP_URL = "http://host.docker.internal:8080" }
if (-not $env:ONLYOFFICE_ENABLED) { $env:ONLYOFFICE_ENABLED = "1" }

Write-Host ""
Write-Host "BauPass lokal (ruhig, ohne Invoice/IMAP-Jobs):" -ForegroundColor Green
Write-Host "  Admin:       http://127.0.0.1:8080/admin-v2/index.html"
Write-Host "  Legacy:      http://127.0.0.1:8080/index.html"
Write-Host "  Docs-Editor: http://127.0.0.1:8080/admin-v2/docs.html"
Write-Host "  OnlyOffice:  $($env:ONLYOFFICE_URL)  (Word Pro — Docker: .\deploy\start-onlyoffice.ps1)"
Write-Host "  Mitarbeiter: http://127.0.0.1:8080/emp-app.html"
Write-Host ""
Write-Host "Login-Tipp: Superadmin oft superadmin / 1234 (Scope Server-Admin)." -ForegroundColor Cyan
Write-Host "Nur 127.0.0.1:8080 oder localhost:8080 oeffnen — nicht Railway." -ForegroundColor Yellow
Write-Host "Beenden: Strg+C" -ForegroundColor Yellow
Write-Host ""

& $python backend\server.py
