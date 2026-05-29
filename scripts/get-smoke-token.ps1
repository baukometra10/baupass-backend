# Obtain a JWT for CI smoke tests (BAUPASS_SMOKE_TOKEN). Does not print password.
param(
    [string]$BaseUrl = $env:PUBLIC_BASE_URL,
    [string]$User = $env:BAUPASS_SMOKE_USER,
    [string]$Password = $env:BAUPASS_SMOKE_PASSWORD,
    [string]$LoginScope = "superadmin"
)

if (-not $BaseUrl) {
    $BaseUrl = Read-Host "Production URL (e.g. https://baupass-production.up.railway.app)"
}
$BaseUrl = $BaseUrl.TrimEnd("/")

if (-not $User) { $User = Read-Host "Username" }
if (-not $Password) {
    $sec = Read-Host "Password" -AsSecureString
    $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    )
}

$body = @{
    username   = $User
    password   = $Password
    loginScope = $LoginScope
} | ConvertTo-Json

try {
    $r = Invoke-RestMethod -Method POST -Uri "$BaseUrl/api/login" -Body $body -ContentType "application/json" -TimeoutSec 30
    if (-not $r.token) { throw "No token in response" }
    Write-Host ""
    Write-Host "GitHub repo secret:" -ForegroundColor Cyan
    Write-Host "  Name:  BAUPASS_SMOKE_TOKEN"
    Write-Host "  Value: (copied below — expires like normal session)"
    Write-Host ""
    $r.token
    Write-Host ""
    Write-Host "Test locally:" -ForegroundColor DarkGray
    Write-Host "  `$env:BAUPASS_SMOKE_TOKEN = '<paste>'"
    Write-Host "  python backend/ops/e2e_production_smoke.py --base-url $BaseUrl"
}
catch {
    Write-Host "Login failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
