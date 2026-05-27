# Automated field-test prelude (API + pages). NFC on device is still manual.
param(
    [string]$BaseUrl = $env:PUBLIC_BASE_URL,
    [string]$User = "superadmin",
    [string]$Password = "1234"
)

if (-not $BaseUrl) {
    $BaseUrl = Read-Host "Base URL"
}
$BaseUrl = $BaseUrl.TrimEnd("/")
$fail = 0

function Assert-Ok($name, $script) {
    try {
        & $script
        Write-Host "[OK] $name" -ForegroundColor Green
    }
    catch {
        Write-Host "[FAIL] $name — $($_.Exception.Message)" -ForegroundColor Red
        $script:fail++
    }
}

Write-Host "Field test prelude: $BaseUrl" -ForegroundColor Cyan

Assert-Ok "health/live" { Invoke-RestMethod "$BaseUrl/api/health/live" | Out-Null }
Assert-Ok "enterprise preview" {
    $p = Invoke-RestMethod "$BaseUrl/api/platform/enterprise-catalog/preview"
    if ($p.layerCount -lt 16) { throw "layerCount $($p.layerCount)" }
}
Assert-Ok "setup-status" { Invoke-RestMethod "$BaseUrl/api/platform/setup-status" | Out-Null }

Assert-Ok "login" {
    $body = @{ username = $User; password = $Password; loginScope = "server-admin" } | ConvertTo-Json
    $r = Invoke-RestMethod -Method POST -Uri "$BaseUrl/api/login" -Body $body -ContentType "application/json"
    if (-not $r.token) { throw "no token" }
    $script:token = $r.token
}

if ($token) {
    $h = @{ Authorization = "Bearer $token" }
    Assert-Ok "capabilities" {
        Invoke-RestMethod -Uri "$BaseUrl/api/platform/capabilities" -Headers $h | Out-Null
    }
}

foreach ($path in @("/admin-v2/index.html", "/enterprise-hub.html", "/join.html")) {
    Assert-Ok $path {
        $code = (Invoke-WebRequest -Uri "$BaseUrl$path" -UseBasicParsing).StatusCode
        if ($code -ne 200) { throw "HTTP $code" }
    }
}

Write-Host "`nManual steps: docs/field-test-checklist-AR.md (NFC + Flutter on phone)" -ForegroundColor Cyan
if ($fail -gt 0) { exit 1 }
