# Quick production health check after Railway deploy
param(
    [string]$BaseUrl = $env:PUBLIC_BASE_URL
)

if (-not $BaseUrl) {
    $BaseUrl = Read-Host "Production URL (e.g. https://baupass-production.up.railway.app)"
}
$BaseUrl = $BaseUrl.TrimEnd("/")

Write-Host "Checking $BaseUrl ..." -ForegroundColor Cyan

function Test-Endpoint($path) {
    $url = "$BaseUrl$path"
    try {
        $r = Invoke-RestMethod -Uri $url -TimeoutSec 30
        Write-Host "[OK] $path" -ForegroundColor Green
        return $r
    }
    catch {
        Write-Host "[FAIL] $path — $($_.Exception.Message)" -ForegroundColor Red
        return $null
    }
}

$health = Test-Endpoint "/api/health"
if ($health) {
    $db = $health.db
    if (-not $db -and $health.checks) { $db = $health.checks.database }
    if ($db) {
        Write-Host "  Database persistent: $($db.persistent) path: $($db.path)"
    }
    $redis = $health.checks.redis
    if ($redis) {
        Write-Host "  Redis: $($redis.status) ok=$($redis.ok)"
    }
    if ($health.cloud) {
        Write-Host "  Cloud: provider=$($health.cloud.provider) region=$($health.cloud.region)"
    }
}

$ready = Test-Endpoint "/api/health/ready"
if ($ready -and $ready.status -ne "ready") {
    Write-Host "  WARNING: service not fully ready" -ForegroundColor Yellow
}

Test-Endpoint "/api/health/live" | Out-Null
Test-Endpoint "/api/health/queues" | Out-Null
$dr = Test-Endpoint "/api/health/dr"
if ($dr -and -not $dr.ok) {
    Write-Host "  WARNING: DR posture degraded (backup age / postgres / replica)" -ForegroundColor Yellow
}
Test-Endpoint "/api/v1/public/health" | Out-Null
Test-Endpoint "/worker-build.json" | Out-Null

foreach ($path in @("/admin-v2/index.html", "/enterprise-hub.html", "/enterprise", "/ops-command-center.html")) {
    try {
        $r = Invoke-WebRequest -Uri "$BaseUrl$path" -TimeoutSec 30 -UseBasicParsing
        if ($r.StatusCode -eq 200) {
            Write-Host "[OK] $path" -ForegroundColor Green
        }
    }
    catch {
        Write-Host "[FAIL] $path — $($_.Exception.Message)" -ForegroundColor Red
    }
}

$preview = Test-Endpoint "/api/platform/enterprise-catalog/preview"
if ($preview -and $preview.layerCount -ge 16) {
    Write-Host "  Enterprise catalog: $($preview.layerCount) layers" -ForegroundColor Green
}

Write-Host "Done." -ForegroundColor Cyan
