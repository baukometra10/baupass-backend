# WorkPass Lohn — one-time platform link (superadmin)
# Usage:
#   .\deploy\link-workpass-lohn.ps1 `
#     -BaseUrl "https://lohn.example.com" `
#     -MasterKey "your-shared-master-key" `
#     -PlatformUrl "https://suppix-ai-workpass.com" `
#     -ApiBase "https://suppix-ai-workpass.com" `
#     -Username "superadmin" `
#     -Password "****"
#
# Optional: -TestOnly to ping current link without saving.

param(
    [string]$ApiBase = "http://127.0.0.1:8080",
    [string]$BaseUrl = "",
    [string]$MasterKey = "",
    [string]$PlatformUrl = "https://suppix-ai-workpass.com",
    [string]$CompanyUpsertPath = "/v1/company/upsert",
    [string]$HoursWebhookPath = "/hooks/suppix-hours",
    [int]$RunDay = 1,
    [switch]$Disable,
    [switch]$TestOnly,
    [string]$Username = "superadmin",
    [string]$Password = ""
)

$ErrorActionPreference = "Stop"
$ApiBase = $ApiBase.TrimEnd("/")

function Invoke-Json {
    param([string]$Method, [string]$Path, [hashtable]$Body = $null, [string]$Token = "")
    $headers = @{ Accept = "application/json" }
    if ($Token) { $headers["Authorization"] = "Bearer $Token" }
    $uri = "$ApiBase$Path"
    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
    }
    $json = $Body | ConvertTo-Json -Compress -Depth 6
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body $json
}

Write-Host "API: $ApiBase" -ForegroundColor Cyan

if (-not $Password) {
    $secure = Read-Host "Superadmin password" -AsSecureString
    $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    )
}

$login = Invoke-Json -Method POST -Path "/api/login" -Body @{
    username = $Username
    password = $Password
    scope    = "server-admin"
}
$token = $login.token
if (-not $token) { throw "Login failed — no token" }
Write-Host "Logged in as $Username" -ForegroundColor Green

$current = Invoke-Json -Method GET -Path "/api/payroll/accounting/platform-link" -Token $token
Write-Host ("Current link: enabled={0} base={1}" -f $current.link.enabled, $current.link.baseUrl) -ForegroundColor Yellow

if ($TestOnly) {
    try {
        $test = Invoke-Json -Method POST -Path "/api/payroll/accounting/platform-link/test" -Token $token -Body @{}
        Write-Host ("Test OK: {0} {1}" -f $test.status, $test.url) -ForegroundColor Green
    } catch {
        Write-Host ("Test failed: {0}" -f $_.Exception.Message) -ForegroundColor Red
        exit 1
    }
    exit 0
}

if (-not $BaseUrl -and -not $Disable) {
    throw "Provide -BaseUrl (WorkPass Lohn host) or use -Disable / -TestOnly"
}

$payload = @{
    enabled            = -not $Disable.IsPresent
    autoProvision      = $true
    baseUrl            = $BaseUrl
    platformPublicUrl  = $PlatformUrl
    companyUpsertPath  = $CompanyUpsertPath
    hoursWebhookPath   = $HoursWebhookPath
    runDay             = $RunDay
}
if ($MasterKey) { $payload.masterApiKey = $MasterKey }

$saved = Invoke-Json -Method POST -Path "/api/payroll/accounting/platform-link" -Token $token -Body $payload
Write-Host ("Saved: enabled={0} base={1} keySet={2}" -f $saved.link.enabled, $saved.link.baseUrl, $saved.link.masterApiKeySet) -ForegroundColor Green

try {
    $test = Invoke-Json -Method POST -Path "/api/payroll/accounting/platform-link/test" -Token $token -Body @{}
    Write-Host ("Connectivity: OK ({0}) {1}" -f $test.status, $test.url) -ForegroundColor Green
} catch {
    Write-Host ("Connectivity warning: {0}" -f $_.Exception.Message) -ForegroundColor Yellow
    Write-Host "Link is saved. Fix Lohn host reachability, then re-run with -TestOnly." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1) In WorkPass Lohn API-Bridge set platform URLs to $PlatformUrl/api/v2/accounting/..."
Write-Host "  2) Enable a company: Einstellungen → WorkPass Lohn aktivieren"
Write-Host "  3) Test hours pull for that Firma-ID"
