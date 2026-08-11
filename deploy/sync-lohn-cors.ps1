# Sync SUPPIX + tenant access_host origins into WorkPass Lohn CORS allow-list.
# Usage:
#   .\deploy\sync-lohn-cors.ps1 -ApiBase "https://suppix-ai-workpass.com" -Username "superadmin"
#
# Requires: company-admin/superadmin login. Backend pushes origins via
# POST {lohn}/v1/platform/cors-origins (master key).

param(
    [string]$ApiBase = "https://suppix-ai-workpass.com",
    [string]$Username = "superadmin",
    [string]$Password = ""
)

$ErrorActionPreference = "Stop"
$ApiBase = $ApiBase.TrimEnd("/")

if (-not $Password) {
    $secure = Read-Host "Password for $Username" -AsSecureString
    $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    )
}

$login = Invoke-RestMethod -Method POST -Uri "$ApiBase/api/login" -ContentType "application/json" -Body (@{
    username = $Username
    password = $Password
    scope    = "server-admin"
} | ConvertTo-Json)
$token = $login.token
if (-not $token) { throw "Login failed" }

$headers = @{ Authorization = "Bearer $token"; Accept = "application/json" }

# Trigger via platform-link test/save side-effect: re-POST current link (no field changes)
$link = Invoke-RestMethod -Method GET -Uri "$ApiBase/api/payroll/accounting/platform-link" -Headers $headers
$payload = @{
    enabled           = [bool]$link.link.enabled
    autoProvision     = [bool]$link.link.autoProvision
    baseUrl           = $link.link.baseUrl
    platformPublicUrl = $link.link.platformPublicUrl
    companyUpsertPath = $link.link.companyUpsertPath
    hoursWebhookPath  = $link.link.hoursWebhookPath
    runDay            = $link.link.runDay
}
if ($link.link.uiBaseUrl) { $payload.uiBaseUrl = $link.link.uiBaseUrl }

$saved = Invoke-RestMethod -Method POST -Uri "$ApiBase/api/payroll/accounting/platform-link" -Headers $headers -ContentType "application/json" -Body ($payload | ConvertTo-Json -Depth 5)
Write-Host ("Platform link saved; CORS sync attempted. enabled={0} base={1}" -f $saved.link.enabled, $saved.link.baseUrl) -ForegroundColor Green
Write-Host "Verify: curl $($saved.link.baseUrl)/v1/platform/cors-origins -H `"X-WorkPass-Key: ***`"" -ForegroundColor DarkGray
