# Enterprise go-live validation after Railway deploy (env + live API)
param(
    [string]$BaseUrl = $env:PUBLIC_BASE_URL,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "BauPass Enterprise Go-Live Check" -ForegroundColor Cyan
Write-Host ""

# 1) Local env validation (Railway CLI injects vars when run in service shell)
$envArgs = @("backend/ops/validate_enterprise_env.py", "--json-only")
if ($BaseUrl) {
    $envArgs += @("--base-url", $BaseUrl.TrimEnd("/"))
}
if ($Strict) {
    $envArgs += "--strict"
}

Push-Location $root
try {
    $json = python @envArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host $json
        Write-Host ""
        Write-Host "FAILED — fix critical items above (see docs/enterprise-go-live-AR.md)" -ForegroundColor Red
        exit 2
    }
    $report = $json | ConvertFrom-Json
    Write-Host "Env score: $($report.env.scorePercent)%" -ForegroundColor Green
    if ($report.live) {
        $liveOk = $report.live.ok
        Write-Host "Live API: $(if ($liveOk) { 'OK' } else { 'FAILED' })" -ForegroundColor $(if ($liveOk) { 'Green' } else { 'Red' })
    }
    if ($report.env.criticalFailures -and $report.env.criticalFailures.Count -gt 0) {
        Write-Host "Critical:" ($report.env.criticalFailures -join ", ") -ForegroundColor Yellow
    }
    if ($report.env.recommendedGaps -and $report.env.recommendedGaps.Count -gt 0) {
        Write-Host "Recommended gaps:" ($report.env.recommendedGaps -join ", ") -ForegroundColor DarkYellow
    }
    Write-Host ""
    Write-Host "Tier: $($report.tier)" -ForegroundColor Cyan

    if ($BaseUrl) {
        Write-Host ""
        Write-Host "Running health sweep..." -ForegroundColor Cyan
        & "$root\deploy\railway-health-check.ps1" -BaseUrl $BaseUrl
    }
}
finally {
    Pop-Location
}
