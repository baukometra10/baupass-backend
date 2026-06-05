# BauPass — Stripe catalog bootstrap + Railway variables
# Usage:
#   $env:STRIPE_SECRET_KEY = "sk_test_..."
#   powershell -ExecutionPolicy Bypass -File .\deploy\railway-stripe-setup.ps1
#
# Optional webhook secret (set manually in Stripe Dashboard first):
#   $env:STRIPE_WEBHOOK_SECRET = "whsec_..."
#
# Dry-run (no Stripe API):
#   powershell -ExecutionPolicy Bypass -File .\deploy\railway-stripe-setup.ps1 -DryRun

param(
    [switch]$DryRun,
    [switch]$SkipRailway,
    [string]$ProductionUrl = "https://baupass-production.up.railway.app"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "`n=== BauPass Stripe Setup ===" -ForegroundColor Cyan

if (-not $DryRun -and -not $env:STRIPE_SECRET_KEY) {
    Write-Host "ERROR: Set STRIPE_SECRET_KEY (sk_test_... or sk_live_...)" -ForegroundColor Red
    Write-Host '  $env:STRIPE_SECRET_KEY = "sk_test_..."' -ForegroundColor Yellow
    exit 1
}

$pyArgs = @("backend/ops/setup_stripe_products.py")
if ($DryRun) { $pyArgs += "--dry-run" }

Write-Host "Running bootstrap..." -ForegroundColor Cyan
$json = & python @pyArgs 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host $json -ForegroundColor Red
    exit 1
}

# Parse JSON block from script output (last JSON object)
$start = $json.LastIndexOf("{")
$result = $null
if ($start -ge 0) {
    try {
        $result = $json.Substring($start) | ConvertFrom-Json
    } catch {
        Write-Host $json
        Write-Host "Could not parse bootstrap JSON." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host $json
    exit 1
}

Write-Host "`n--- Stripe products ---" -ForegroundColor Green
$result.created | ForEach-Object {
    Write-Host "  $($_.plan): monthly=$($_.monthlyPriceId) annual=$($_.annualPriceId)"
}

Write-Host "`n--- Env vars ---" -ForegroundColor Cyan
$envVars = @{}
$envVars["BAUPASS_STRIPE_TRIAL_DAYS"] = "14"
if ($env:STRIPE_WEBHOOK_SECRET) {
    $envVars["STRIPE_WEBHOOK_SECRET"] = $env:STRIPE_WEBHOOK_SECRET
}
foreach ($prop in $result.env.PSObject.Properties) {
    $envVars[$prop.Name] = [string]$prop.Value
    Write-Host "  $($prop.Name)=$($prop.Value)"
}
Write-Host "  BAUPASS_STRIPE_TRIAL_DAYS=14"

$webhookUrl = "$($ProductionUrl.TrimEnd('/'))/api/billing/stripe/webhook"
Write-Host "`n--- Stripe Dashboard webhook ---" -ForegroundColor Cyan
Write-Host "  URL: $webhookUrl"
Write-Host "  Events: checkout.session.completed, customer.subscription.*, invoice.paid, invoice.payment_failed, payment_intent.succeeded"

if ($SkipRailway) {
    Write-Host "`nSkipRailway: paste vars into Railway manually." -ForegroundColor Yellow
    exit 0
}

if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Write-Host "`nRailway CLI missing — install: npm i -g @railway/cli" -ForegroundColor Yellow
    exit 0
}

$who = railway whoami 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nRailway not logged in. Run:" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\deploy\fix-railway-login.ps1"
    exit 0
}

if (-not (Test-Path (Join-Path $Root ".railway"))) {
    Write-Host "`nLink project: railway link (baupass-production / web)" -ForegroundColor Yellow
    railway link
}

if (-not $DryRun -and $env:STRIPE_SECRET_KEY) {
    $envVars["STRIPE_SECRET_KEY"] = $env:STRIPE_SECRET_KEY
}

Write-Host "`nSetting Railway variables..." -ForegroundColor Cyan
foreach ($entry in $envVars.GetEnumerator()) {
    railway variables set "$($entry.Key)=$($entry.Value)" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK $($entry.Key)" -ForegroundColor Green
    } else {
        Write-Host "  FAIL $($entry.Key)" -ForegroundColor Red
    }
}

Write-Host "`nDone. Redeploy if needed: railway up" -ForegroundColor Green
Write-Host "Verify: curl $ProductionUrl/api/platform/setup-status`n" -ForegroundColor Cyan
