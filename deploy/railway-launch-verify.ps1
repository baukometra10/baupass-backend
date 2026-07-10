# SUPPIX production smoke — run after deploy
param(
    [string]$BaseUrl = "https://suppix-workpass-ai.up.railway.app"
)

$ErrorActionPreference = "Stop"
$base = $BaseUrl.TrimEnd("/")

function Test-Endpoint($path, $expectJson = $true) {
    $url = "$base$path"
    Write-Host "GET $url" -ForegroundColor Cyan
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30
    if ($r.StatusCode -ge 400) { throw "HTTP $($r.StatusCode) for $path" }
    if ($expectJson) {
        $null = $r.Content | ConvertFrom-Json
    }
    Write-Host "  OK $($r.StatusCode)" -ForegroundColor Green
}

Write-Host "`n=== SUPPIX Launch Verify ===" -ForegroundColor Yellow
Test-Endpoint "/api/health"
Test-Endpoint "/worker-join-config.json"
Test-Endpoint "/api/worker-app/mobile-setup"
try {
    Test-Endpoint "/.well-known/assetlinks.json"
} catch {
    Write-Host "  SKIP assetlinks (set BAUPASS_ANDROID_APP_LINK_SHA256)" -ForegroundColor DarkYellow
}
Write-Host "`nDone. Run E2E checklist: docs/qr-worker-e2e-checklist-DE.md" -ForegroundColor Green
