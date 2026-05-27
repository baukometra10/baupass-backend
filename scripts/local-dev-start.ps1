# BauPass local dev — Backend on port 8080 (Python 3.11 venv)
# Usage: .\scripts\local-dev-start.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Py311 = "$env:APPDATA\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe"
if (-not (Test-Path $Py311)) {
    Write-Host "Python 3.11 not found at $Py311" -ForegroundColor Red
    Write-Host "Install: winget install Python.Python.3.11  OR  uv python install 3.11"
    exit 1
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv with Python 3.11..." -ForegroundColor Cyan
    & $Py311 -m venv .venv
    .\.venv\Scripts\pip install -r backend\requirements.txt
}

$env:BAUPASS_ENABLE_BACKGROUND_JOBS = "0"
$env:BAUPASS_ENABLE_IMAP_POLLER = "0"
$env:PORT = "8080"

Write-Host ""
Write-Host "Starting backend at http://127.0.0.1:8080" -ForegroundColor Green
Write-Host "  Admin v2:  http://127.0.0.1:8080/admin-v2/index.html" -ForegroundColor Green
Write-Host "  Legacy:    http://127.0.0.1:8080/index.html" -ForegroundColor Green
Write-Host "  Worker PWA: http://127.0.0.1:8080/emp-app.html" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

.\.venv\Scripts\python.exe backend\server.py
