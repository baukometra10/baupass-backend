# PostgreSQL Staging verification (Windows)
param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,
    [string]$Token = ""
)

$ErrorActionPreference = "Stop"
$base = $BaseUrl.TrimEnd("/")

Write-Host "== PostgreSQL / platform staging verify ==" -ForegroundColor Cyan
Write-Host "Target: $base"

Write-Host "`n[1] Preflight (local DATABASE_URL)..." -ForegroundColor Yellow
if (-not $env:DATABASE_URL) {
    Write-Warning "DATABASE_URL not set — skip local preflight (set it to run postgres_preflight.py)"
} else {
    python backend/ops/postgres_preflight.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Invoke-Health($path) {
    $url = "$base$path"
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30
        Write-Host "  OK $path -> $($r.StatusCode)" -ForegroundColor Green
        return $r.Content
    } catch {
        Write-Host "  FAIL $path -> $($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

Write-Host "`n[2] Health endpoints..." -ForegroundColor Yellow
Invoke-Health "/api/health/live" | Out-Null
$ready = Invoke-Health "/api/health/ready"
$full = Invoke-Health "/api/health"

if ($full -match '"backend"\s*:\s*"postgres"') {
    Write-Host "  PostgreSQL runtime detected in health payload" -ForegroundColor Green
} else {
    Write-Warning "  PostgreSQL backend not reported — BAUPASS_PG_RUNTIME may be off"
}

Write-Host "`n[3] OpenAPI spec..." -ForegroundColor Yellow
Invoke-Health "/api/v1/openapi.json" | Out-Null

if ($Token) {
    Write-Host "`n[4] Authenticated database-status..." -ForegroundColor Yellow
    $headers = @{ Authorization = "Bearer $Token" }
    $r = Invoke-WebRequest -Uri "$base/api/platform/database-status" -Headers $headers -UseBasicParsing
    Write-Host "  database-status -> $($r.StatusCode)" -ForegroundColor Green
    Write-Host $r.Content
}

Write-Host "`nDone. See docs/postgres-staging-checklist-AR.md for full checklist." -ForegroundColor Cyan
