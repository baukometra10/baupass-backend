# BauPass — Push Apple/Google Wallet secrets to Railway
# Usage (from repo root, Railway CLI linked to production web service):
#   powershell -ExecutionPolicy Bypass -File .\deploy\railway-wallet-setup.ps1
# Dry-run (print keys, no railway set):
#   powershell -ExecutionPolicy Bypass -File .\deploy\railway-wallet-setup.ps1 -DryRun
#
# Optional overrides via env before running:
#   $env:APPLE_TEAM_ID = "..."
#   $env:APPLE_PASS_TYPE_ID = "pass...."
#   $env:APPLE_CERT_PASSWORD = "..."
#   $env:GOOGLE_ISSUER_ID = "..."

param(
    [switch]$DryRun,
    [switch]$SkipApple,
    [switch]$SkipGoogle,
    [string]$WalletDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $WalletDir) {
    $WalletDir = Join-Path $Root "backend\wallet"
}

Write-Host "`n=== BauPass Railway Wallet Setup ===" -ForegroundColor Cyan
Write-Host "Wallet dir: $WalletDir"

function Set-RailwayVar([string]$Name, [string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        Write-Host "  skip $Name (empty)" -ForegroundColor DarkYellow
        return
    }
    if ($DryRun) {
        $preview = if ($Value.Length -gt 48) { $Value.Substring(0, 48) + "..." } else { $Value }
        Write-Host "  DRY $Name = $preview" -ForegroundColor Gray
        return
    }
    railway variables set "$Name=$Value" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "railway variables set failed for $Name"
    }
    Write-Host "  set $Name" -ForegroundColor Green
}

function Get-FileBase64([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    return [Convert]::ToBase64String([IO.File]::ReadAllBytes($Path))
}

$vars = @{}

if (-not $SkipApple) {
    $p12 = Join-Path $WalletDir "apple-passkit.p12"
    $cer = Join-Path $WalletDir "apple-intermediate.cer"
    if (-not (Test-Path $p12) -and -not $env:APPLE_CERT_BASE64) {
        Write-Host "Apple: missing $p12 (and no APPLE_CERT_BASE64 in env). See docs/apple-wallet-setup-guide.md" -ForegroundColor Yellow
    } else {
        $vars["APPLE_TEAM_ID"] = $env:APPLE_TEAM_ID
        $vars["APPLE_PASS_TYPE_ID"] = $env:APPLE_PASS_TYPE_ID
        $vars["APPLE_CERT_PASSWORD"] = $env:APPLE_CERT_PASSWORD
        $vars["APPLE_CERT_BASE64"] = if ($env:APPLE_CERT_BASE64) { $env:APPLE_CERT_BASE64 } else { Get-FileBase64 $p12 }
        $vars["APPLE_INTERMEDIATE_CERT_BASE64"] = if ($env:APPLE_INTERMEDIATE_CERT_BASE64) {
            $env:APPLE_INTERMEDIATE_CERT_BASE64
        } else {
            Get-FileBase64 $cer
        }
        if (-not $vars["APPLE_TEAM_ID"] -or -not $vars["APPLE_PASS_TYPE_ID"]) {
            Write-Host "Apple: set APPLE_TEAM_ID and APPLE_PASS_TYPE_ID in the shell before running." -ForegroundColor Yellow
        }
        if ($null -eq $vars["APPLE_CERT_PASSWORD"]) {
            Write-Host "Apple: APPLE_CERT_PASSWORD empty — ok only if .p12 has no password." -ForegroundColor DarkYellow
        }
    }
}

if (-not $SkipGoogle) {
    $sa = Join-Path $WalletDir "google-service-account.json"
    if (-not (Test-Path $sa) -and -not $env:GOOGLE_SERVICE_ACCOUNT_JSON) {
        Write-Host "Google: missing $sa (and no GOOGLE_SERVICE_ACCOUNT_JSON). See docs/google-wallet-setup-guide.md" -ForegroundColor Yellow
    } else {
        $jsonText = if ($env:GOOGLE_SERVICE_ACCOUNT_JSON) {
            $env:GOOGLE_SERVICE_ACCOUNT_JSON
        } else {
            [IO.File]::ReadAllText($sa)
        }
        $saObj = $jsonText | ConvertFrom-Json
        $vars["GOOGLE_SERVICE_ACCOUNT_JSON"] = $jsonText.Trim()
        $vars["GOOGLE_PROJECT_ID"] = if ($env:GOOGLE_PROJECT_ID) { $env:GOOGLE_PROJECT_ID } else { [string]$saObj.project_id }
        $vars["GOOGLE_SERVICE_ACCOUNT_EMAIL"] = if ($env:GOOGLE_SERVICE_ACCOUNT_EMAIL) {
            $env:GOOGLE_SERVICE_ACCOUNT_EMAIL
        } else {
            [string]$saObj.client_email
        }
        $vars["GOOGLE_ISSUER_ID"] = $env:GOOGLE_ISSUER_ID
        if ($env:GOOGLE_WALLET_CLASS_ID) {
            $vars["GOOGLE_WALLET_CLASS_ID"] = $env:GOOGLE_WALLET_CLASS_ID
        }
        if (-not $vars["GOOGLE_ISSUER_ID"]) {
            Write-Host "Google: set GOOGLE_ISSUER_ID in the shell before running." -ForegroundColor Yellow
        }
    }
}

if (-not $DryRun) {
    $null = Get-Command railway -ErrorAction Stop
}

Write-Host "`nApplying variables..." -ForegroundColor Cyan
foreach ($key in ($vars.Keys | Sort-Object)) {
    Set-RailwayVar $key $vars[$key]
}

Write-Host "`nNext:" -ForegroundColor Cyan
Write-Host "  1. Redeploy web (if Railway did not auto-restart)"
Write-Host "  2. Admin → Platform → Wallet status"
Write-Host "  3. GET /api/admin/wallet/runtime-status"
Write-Host "  Docs: docs/railway-wallet-setup.md"
if ($DryRun) {
    Write-Host "`nDry-run only — no railway variables were changed." -ForegroundColor Yellow
}
