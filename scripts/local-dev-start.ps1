# BauPass local dev — Backend on port 8080 (quiet: no IMAP/invoice background spam)
# Usage: .\scripts\local-dev-start.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
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
    $Py311 = Join-Path $env:APPDATA "uv\python\cpython-3.11.15-windows-x86_64-none\python.exe"
    if (Test-Path $Py311) { return $Py311 }
    return $null
}

$python = Resolve-LocalPython
if (-not $python) {
    Write-Host "Kein Python/venv gefunden. Bitte .venv-ci oder .venv311 anlegen." -ForegroundColor Red
    exit 1
}

$env:HOST = "0.0.0.0"
$env:PORT = "8080"
$env:PUBLIC_BASE_URL = "http://127.0.0.1:8080"
$env:BAUPASS_ENV = "development"
$env:BAUPASS_ENABLE_BACKGROUND_JOBS = "0"
$env:BAUPASS_ENABLE_IMAP_POLLER = "0"
$env:BAUPASS_SKIP_IMAP_POLL = "1"
$env:BAUPASS_DB_PATH = Join-Path $Root "backend\baupass.db"

Write-Host ""
Write-Host "Starting quiet local backend at http://127.0.0.1:8080" -ForegroundColor Green
Write-Host "  Admin v2:    http://127.0.0.1:8080/admin-v2/index.html"
Write-Host "  Docs editor: http://127.0.0.1:8080/admin-v2/docs.html"
Write-Host "  Legacy:      http://127.0.0.1:8080/index.html"
Write-Host "  Worker PWA:  http://127.0.0.1:8080/emp-app.html"
Write-Host ""
Write-Host "Python: $(& $python --version)" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

& $python backend\server.py
