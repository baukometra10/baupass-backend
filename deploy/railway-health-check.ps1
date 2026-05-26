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
    $db = $health.checks.database
    Write-Host "  Database persistent: $($db.persistent) path: $($db.path)"
    if ($health.checks.redis) {
        Write-Host "  Redis: $($health.checks.redis.status)"
    }
}

Test-Endpoint "/api/health/live" | Out-Null
Test-Endpoint "/api/health/ready" | Out-Null
Test-Endpoint "/api/health/queues" | Out-Null
Test-Endpoint "/api/v1/public/health" | Out-Null
Test-Endpoint "/worker-build.json" | Out-Null

Write-Host "Done." -ForegroundColor Cyan
