# Trigger GitHub Actions workflow "mobile-release" (APK + GitHub Release).
param(
    [string]$Repo = "baukometra10/baupass-backend",
    [string]$ApiBaseUrl = "https://suppix-workpass-ai.up.railway.app",
    [string]$GitHubToken = $env:GITHUB_TOKEN,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$actionsUrl = "https://github.com/$Repo/actions/workflows/mobile-release.yml"

if (-not $GitHubToken) {
    Write-Host "GITHUB_TOKEN nicht gesetzt — manueller Start:" -ForegroundColor Yellow
    Write-Host "  1. $actionsUrl"
    Write-Host "  2. Run workflow → api_base_url = $ApiBaseUrl"
    Write-Host "  3. Nach grünem Job: Release-URL → Railway BAUPASS_WORKER_APK_URL"
    if ($OpenBrowser) { Start-Process $actionsUrl }
    exit 0
}

$body = @{
    ref = "main"
    inputs = @{
        api_base_url = $ApiBaseUrl
    }
} | ConvertTo-Json

$headers = @{
    Authorization = "Bearer $GitHubToken"
    Accept        = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}

Write-Host "Starte mobile-release für $Repo …" -ForegroundColor Cyan
Invoke-RestMethod `
    -Uri "https://api.github.com/repos/$Repo/actions/workflows/mobile-release.yml/dispatches" `
    -Method Post `
    -Headers $headers `
    -Body $body `
    -ContentType "application/json"

Write-Host "Workflow gestartet. Status: $actionsUrl" -ForegroundColor Green
if ($OpenBrowser) { Start-Process $actionsUrl }
