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
if ($ready -and $ready.ready -eq $false) {
    Write-Host "  WARNING: service not fully ready" -ForegroundColor Yellow
}

Test-Endpoint "/api/health/live" | Out-Null

$platform = Test-Endpoint "/api/health/platform"
if ($platform) {
    $st = $platform.status
    Write-Host "  Platform status: $st" -ForegroundColor $(if ($st -eq "ok") { "Green" } else { "Yellow" })
    foreach ($probe in @($platform.probes)) {
        $color = if ($probe.ok) { "Green" } else { "Red" }
        Write-Host ('    {0}: {1} ({2} ms)' -f $probe.id, $probe.detail, $probe.latencyMs) -ForegroundColor $color
    }
} else {
    Write-Host '  Platform health: not deployed yet (deploy latest code + redeploy)' -ForegroundColor Yellow
}
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

$setup = Test-Endpoint "/api/platform/setup-status"
if ($setup) {
    Write-Host "  Setup score: $($setup.readyScore.percent)% (missing: $($setup.readyScore.missing.Count))" -ForegroundColor $(if ($setup.readyScore.percent -ge 80) { "Green" } else { "Yellow" })
    $db = $setup.database
    if ($db) {
        $loginColor = if ($db.loginReady) { "Green" } else { "Red" }
        Write-Host "  DB login ready: $($db.loginReady) | file exists: $($db.sqliteFileExists) | size: $($db.sqliteSizeBytes) B | persistent: $($db.persistent)" -ForegroundColor $loginColor
        if ($db.railwayHints -and $db.railwayHints.Count -gt 0) {
            foreach ($hint in $db.railwayHints) {
                Write-Host "    -> $hint" -ForegroundColor Yellow
            }
        }
        if (-not $db.loginReady) {
            Write-Host "  FIX: Railway -> Service -> Volume mount /data -> Variables:" -ForegroundColor Cyan
            Write-Host "       BAUPASS_PG_RUNTIME=0" -ForegroundColor Cyan
            Write-Host "       BAUPASS_DB_PATH=/data/baupass.db" -ForegroundColor Cyan
            Write-Host "       Then Redeploy and re-run this script." -ForegroundColor Cyan
        }
    }
}

# Login probe — should not return database_not_ready when DB is healthy.
try {
    $loginProbe = Invoke-RestMethod -Uri "$BaseUrl/api/login" -Method Post -ContentType "application/json" -Body '{"username":"__health_probe__","password":"x"}' -TimeoutSec 20
}
catch {
    $loginProbe = $null
    $statusCode = $null
    if ($_.Exception.Response) {
        $statusCode = [int]$_.Exception.Response.StatusCode
    }
    if ($statusCode -eq 503) {
        Write-Host '[FAIL] /api/login returns 503 (database_not_ready) - fix Volume + BAUPASS_DB_PATH' -ForegroundColor Red
    }
    elseif ($statusCode -eq 401 -or $statusCode -eq 400) {
        Write-Host '[OK] /api/login reachable (auth rejected as expected)' -ForegroundColor Green
    }
    else {
        Write-Host ('[WARN] /api/login probe: HTTP ' + $statusCode) -ForegroundColor Yellow
    }
}

Write-Host "Done." -ForegroundColor Cyan
