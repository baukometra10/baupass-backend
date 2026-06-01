# Compare local main vs production deploy + smoke UI/API assets
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\deploy\verify-production-deploy.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy\verify-production-deploy.ps1 -BaseUrl https://baupass-production.up.railway.app
param(
    [string]$BaseUrl = "https://baupass-production.up.railway.app"
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$BaseUrl = $BaseUrl.TrimEnd("/")

function Get-ShortSha([string]$sha) {
    if (-not $sha) { return "" }
    return $sha.Substring(0, [Math]::Min(7, $sha.Length))
}

Write-Host "`n=== BauPass Production Deploy Check ===" -ForegroundColor Cyan
Write-Host "URL: $BaseUrl`n"

$localSha = ""
try {
    $localSha = (git rev-parse HEAD 2>$null).Trim()
    Write-Host "Local HEAD:  $(Get-ShortSha $localSha) $localSha" -ForegroundColor Gray
}
catch {
    Write-Host "Local git HEAD unavailable." -ForegroundColor Yellow
}

$health = $null
try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -TimeoutSec 35
}
catch {
    Write-Host "[FAIL] /api/health - $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

$remoteSha = ""
if ($health.deploy.railwayGitCommit) { $remoteSha = $health.deploy.railwayGitCommit }
elseif ($health.cloud.gitCommit) { $remoteSha = $health.cloud.gitCommit }
Write-Host "Production:  $(Get-ShortSha $remoteSha) $remoteSha" -ForegroundColor Gray

if ($localSha -and $remoteSha) {
    if ($localSha.StartsWith($remoteSha.Substring(0, 7)) -or $remoteSha.StartsWith($localSha.Substring(0, 7))) {
        Write-Host "[OK] Production matches local HEAD (Railway deployed latest push)." -ForegroundColor Green
    }
    else {
        Write-Host "[WARN] Production is NOT on local HEAD - wait 2-5 min or Redeploy in Railway." -ForegroundColor Yellow
        Write-Host "       Railway Dashboard -> baupass-production -> Deployments -> Redeploy" -ForegroundColor Yellow
    }
}

$db = $health.db
if (-not $db -and $health.checks) { $db = $health.checks.database }
if ($db) {
    $pColor = if ($db.persistent) { "Green" } else { "Red" }
    Write-Host ("[DB] persistent={0} workers={1} path={2}" -f $db.persistent, $db.workersActive, $db.path) -ForegroundColor $pColor
    if (-not $db.persistent) {
        Write-Host "       FIX: Volume mount /data + BAUPASS_DB_PATH=/data/baupass.db" -ForegroundColor Red
    }
}

try {
    $platform = Invoke-RestMethod -Uri "$BaseUrl/api/health/platform" -TimeoutSec 35
    $st = $platform.status
    Write-Host "[OK] /api/health/platform status=$st" -ForegroundColor $(if ($st -eq "ok") { "Green" } else { "Yellow" })
}
catch {
    Write-Host "[FAIL] /api/health/platform - push a91771e+ and redeploy" -ForegroundColor Red
}

try {
    $html = (Invoke-WebRequest -Uri "$BaseUrl/index.html" -UseBasicParsing -TimeoutSec 35).Content
    $checks = @(
        @{ Name = "platform-unified.css"; Ok = ($html -match "platform-unified\.css") },
        @{ Name = "app.js v=20260603uni1"; Ok = ($html -match "app\.js\?v=20260603uni1") },
        @{ Name = "navBetrieb link"; Ok = ($html -match 'id="navBetriebLink"') }
    )
    foreach ($c in $checks) {
        if ($c.Ok) {
            Write-Host "[OK] UI bundle: $($c.Name)" -ForegroundColor Green
        }
        else {
            Write-Host "[WARN] UI bundle missing: $($c.Name) - hard refresh Ctrl+F5 or wait for CDN" -ForegroundColor Yellow
        }
    }
}
catch {
    Write-Host "[FAIL] index.html - $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n--- GitHub Actions backup (optional) ---" -ForegroundColor Cyan
Write-Host "If Railway Git deploy fails, set repo secrets on GitHub:"
Write-Host "  https://github.com/baukometra10/baupass-backend/settings/secrets/actions"
Write-Host "  RAILWAY_TOKEN, RAILWAY_SERVICE_ID, PUBLIC_BASE_URL"
Write-Host "Then: Actions -> railway-deploy -> Run workflow"
Write-Host "Guide: docs/railway-auto-deploy-AR.md`n"

& (Join-Path $PSScriptRoot "railway-health-check.ps1") -BaseUrl $BaseUrl
