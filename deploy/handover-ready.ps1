# BauPass — Handover readiness check (no code changes required)
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\deploy\handover-ready.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy\handover-ready.ps1 -BaseUrl "https://baupass-production.up.railway.app"
param(
    [string]$BaseUrl = $env:PUBLIC_BASE_URL,
    [switch]$Strict
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $BaseUrl) {
    $BaseUrl = "https://baupass-production.up.railway.app"
}
$BaseUrl = $BaseUrl.TrimEnd("/")

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BauPass — Handover Readiness Check" -ForegroundColor Cyan
Write-Host "  URL: $BaseUrl" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$failed = 0

# 1) Enterprise env + live API
Write-Host "[1/4] Enterprise validation..." -ForegroundColor Yellow
$goLiveArgs = @("-BaseUrl", $BaseUrl)
if ($Strict) { $goLiveArgs += "-Strict" }
& (Join-Path $PSScriptRoot "railway-enterprise-go-live.ps1") @goLiveArgs
if ($LASTEXITCODE -ne 0) { $failed++ }

# 2) Setup status (includes cameras block)
Write-Host ""
Write-Host "[2/4] Platform setup-status..." -ForegroundColor Yellow
try {
    $setup = Invoke-RestMethod -Uri "$BaseUrl/api/platform/setup-status" -TimeoutSec 30
    $pct = $setup.readyScore.percent
    Write-Host "  Ready score: $pct%" -ForegroundColor $(if ($pct -ge 80) { "Green" } else { "Yellow" })
    if ($setup.cameras) {
        $rtsp = $setup.cameras.rtspBridgeToken
        Write-Host "  Cameras RTSP token: $(if ($rtsp) { 'SET' } else { 'MISSING — set BAUPASS_RTSP_BRIDGE_TOKEN' })" `
            -ForegroundColor $(if ($rtsp) { "Green" } else { "Yellow" })
    }
    foreach ($m in @($setup.readyScore.missing)) {
        if ($m) { Write-Host "  [ ] $m" -ForegroundColor DarkYellow }
    }
}
catch {
    Write-Host "  setup-status failed: $($_.Exception.Message)" -ForegroundColor Red
    $failed++
}

# 3) Health endpoints
Write-Host ""
Write-Host "[3/4] Health endpoints..." -ForegroundColor Yellow
foreach ($path in @("/api/health", "/api/health/ready", "/api/health/live")) {
    try {
        $r = Invoke-RestMethod -Uri "$BaseUrl$path" -TimeoutSec 20
        $st = $r.status
        Write-Host "  $path -> $st" -ForegroundColor Green
    }
    catch {
        Write-Host "  $path -> FAILED" -ForegroundColor Red
        $failed++
    }
}

# 4) Summary
Write-Host ""
Write-Host "[4/4] Handover summary" -ForegroundColor Yellow
Write-Host "  Doc:  docs/HANDOVER-PLATFORM-AR.md"
Write-Host "  Env:  .env.railway.example"
Write-Host "  Cam:  docs/camera-rtsp-bridge-DE.md"
Write-Host ""

if ($failed -eq 0) {
    Write-Host "HANDOVER READY — Platform operable without code changes." -ForegroundColor Green
    Write-Host "Configure via Railway Variables + Control Pass UI only." -ForegroundColor Green
    exit 0
}

Write-Host "ACTION REQUIRED — $failed check(s) failed. Fix Railway Variables / deploy." -ForegroundColor Red
Write-Host "See docs/HANDOVER-PLATFORM-AR.md section 2." -ForegroundColor Red
exit 2
