# Next launch steps: APK build + RQ worker — checks production and prints exact actions.
param(
    [string]$BaseUrl = "https://suppix-workpass-ai.up.railway.app",
    [switch]$TriggerApkBuild,
    [switch]$OpenRailway,
    [switch]$OpenGitHubActions
)

$ErrorActionPreference = "Continue"
$base = $BaseUrl.TrimEnd("/")
$repo = "baukometra10/baupass-backend"

Write-Host "`n=== SUPPIX Launch — Nächste Schritte ===" -ForegroundColor Yellow
Write-Host "Production: $base`n"

& "$PSScriptRoot\railway-launch-verify.ps1" -BaseUrl $base

$join = $null
$mobile = $null
try {
    $join = Invoke-RestMethod -Uri "$base/worker-join-config.json" -TimeoutSec 30
    $mobile = Invoke-RestMethod -Uri "$base/api/worker-app/mobile-setup" -TimeoutSec 30
}
catch {
    Write-Host "Konfiguration konnte nicht geladen werden: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "`n--- Mobile Distribution ---" -ForegroundColor Cyan
$apkOk = [bool]($join.apkUrl)
$tfOk = [bool]($join.testFlightUrl)
Write-Host ("  APK (BAUPASS_WORKER_APK_URL): " + $(if ($apkOk) { "OK $($join.apkUrl)" } else { "FEHLT" })) `
    -ForegroundColor $(if ($apkOk) { "Green" } else { "Yellow" })
Write-Host ("  TestFlight: " + $(if ($tfOk) { "OK" } else { "FEHLT (iPhone intern)" })) `
    -ForegroundColor $(if ($tfOk) { "Green" } else { "DarkYellow" })

if (-not $apkOk) {
    Write-Host "`n[A] APK bauen & verlinken" -ForegroundColor Yellow
    Write-Host "  Option 1 — GitHub Actions (empfohlen):"
    Write-Host "    .\deploy\trigger-mobile-release.ps1 -OpenBrowser"
    Write-Host "    oder: https://github.com/$repo/actions/workflows/mobile-release.yml"
    Write-Host "  Option 2 — Lokal: cd mobile && flutter build apk --release --dart-define=BAUPASS_API_URL=$base"
    Write-Host "  Danach Railway setzen:"
    Write-Host "    BAUPASS_WORKER_APK_URL=https://github.com/$repo/releases/download/worker-apk-NNN/app-release.apk"
}

Write-Host "`n--- RQ Worker Service ---" -ForegroundColor Cyan
$redisOk = $false
foreach ($k in $mobile.envKeys) {
    if ($k.id -eq "REDIS_URL" -and $k.configured) { $redisOk = $true }
}
Write-Host ("  REDIS_URL: " + $(if ($redisOk) { "konfiguriert" } else { "FEHLT" })) `
    -ForegroundColor $(if ($redisOk) { "Green" } else { "Red" })

Write-Host "`n[B] Railway Worker (zweiter Service)" -ForegroundColor Yellow
Write-Host "  1. railway login && railway link  (oder deploy\railway-login-link.ps1)"
Write-Host "  2. Railway Dashboard → New Service → gleiches Repo"
Write-Host "  3. Start Command: python -m backend.app.tasks.worker"
Write-Host "  4. Volume /data + Variablen von API-Service referenzieren:"
Write-Host "     REDIS_URL, BAUPASS_DB_PATH=/data/baupass.db, BAUPASS_SECRET_KEY, BAUPASS_WORKER_JWT_SECRET"
Write-Host "  5. Optional RQ-Modi: BAUPASS_DAILY_JOBS_MODE=rq, BAUPASS_DUNNING_MODE=rq, …"
Write-Host "  Referenz: deploy/railway-worker.json + deploy/railway-worker.service.md"

$whoami = (railway whoami 2>&1 | Out-String).Trim()
if ($whoami -match "Unauthorized") {
    Write-Host "`n  Railway CLI: nicht eingeloggt → .\deploy\railway-login-link.ps1" -ForegroundColor DarkYellow
}
else {
    Write-Host "`n  Railway CLI: $whoami" -ForegroundColor Green
}

if ($TriggerApkBuild) {
    & "$PSScriptRoot\trigger-mobile-release.ps1" -OpenBrowser:$OpenGitHubActions
}

if ($OpenRailway) {
    Start-Process "https://railway.com/dashboard"
}
if ($OpenGitHubActions -and -not $TriggerApkBuild) {
    Start-Process "https://github.com/$repo/actions/workflows/mobile-release.yml"
}

Write-Host "`nMaster-Checkliste: docs/LAUNCH-SEQUENCE-DE.md" -ForegroundColor Green
Write-Host "E2E nach APK: docs/qr-worker-e2e-checklist-DE.md`n"
