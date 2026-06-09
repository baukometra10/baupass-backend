# Get STPadServerLib.js onto this PC and into BauPass vendor/ folder.
# Run in PowerShell from repo root:  .\scripts\get-signotec-lib.ps1
param(
    [switch]$OpenDownloadPages,
    [switch]$AfterInstall,
    [switch]$Deploy
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $Root "vendor\signotec\STPadServerLib.js"

function Test-SignotecLib([string]$Path) {
    if (-not (Test-Path $Path)) { return $false }
    $head = Get-Content -Path $Path -TotalCount 40 -ErrorAction SilentlyContinue | Out-String
    return $head -match "STPadServerLibCommons"
}

function Find-SignotecLib {
    $candidates = @(
        "C:\Program Files\signotec\signoPAD-API Web\STPadServerLib.js",
        "C:\Program Files (x86)\signotec\signoPAD-API Web\STPadServerLib.js",
        "C:\Program Files\signotec\signoPAD-API\Web\STPadServerLib.js"
    )
    $sampleRoots = @(
        "C:\Program Files\signotec\signoPAD-API Web\Sample",
        "C:\Program Files (x86)\signotec\signoPAD-API Web\Sample"
    )
    foreach ($root in $sampleRoots) {
        if (-not (Test-Path $root)) { continue }
        Get-ChildItem -Path $root -Filter "STPadServerLib*.js" -ErrorAction SilentlyContinue | ForEach-Object {
            $candidates += $_.FullName
        }
    }
    foreach ($path in $candidates) {
        if (Test-SignotecLib $path) { return $path }
    }
    $roots = @(
        "C:\Program Files\signotec",
        "C:\Program Files (x86)\signotec",
        $env:LOCALAPPDATA,
        $env:USERPROFILE + "\Downloads"
    )
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        try {
            $hit = Get-ChildItem -Path $root -Filter "STPadServerLib.js" -Recurse -Depth 6 -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit -and (Test-SignotecLib $hit.FullName)) { return $hit.FullName }
        } catch { }
    }
    return $null
}

function Test-PadServerRunning {
    foreach ($url in @("https://127.0.0.1:49494/STPadServerLib.js", "https://localhost:49494/STPadServerLib.js")) {
        try {
            $r = Invoke-WebRequest -Uri $url -SkipCertificateCheck -TimeoutSec 4
            if ($r.StatusCode -eq 200 -and $r.Content -match "STPadServerLibCommons") {
                return @{ Ok = $true; Url = $url; Content = $r.Content }
            }
        } catch { }
    }
    return @{ Ok = $false }
}

Write-Host ""
Write-Host "=== BauPass: STPadServerLib.js holen ===" -ForegroundColor Cyan
Write-Host ""

if ($OpenDownloadPages -or (-not $AfterInstall)) {
    Write-Host "Schritt 1 - signoPAD-API/Web herunterladen und installieren:" -ForegroundColor Yellow
    Write-Host "  (Pad per USB allein reicht nicht - Middleware-Software noetig)"
    Write-Host ""
    Write-Host "  Direkt-Link (signoPAD-API/Web 3.5.0 - richtiges Paket!):" -ForegroundColor Green
    Write-Host "     https://backend.signotec.com/wp-content/uploads/2025/11/signotec_signoPAD-API_Web_3.5.0.exe"
    Write-Host ""
    Write-Host "  NICHT signoPADTools - das ist ein anderes Paket ohne STPadServerLib.js!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  A) Produktseite (Windows 3.5.0):" -ForegroundColor White
    Write-Host "     https://www.signotec.com/portal/seiten/signotec-signopad-api-web-900000546-10002.html"
    Write-Host "  B) Developer Downloads:" -ForegroundColor White
    Write-Host "     https://en.signotec.com/portal/seiten/download-developer-tools-api-sdk--900000510-10002.html"
    Write-Host "  C) Alle Downloads:" -ForegroundColor White
    Write-Host "     https://en.signotec.com/service/downloads/all-downloads/"
    Write-Host ""
    Write-Host "  Suche auf der Seite: Download signoPAD-API/Web Windows"
    Write-Host "  Installer-Name: signotec_signoPAD-API_Web_3.5.0.exe (aehnlich)"
    Write-Host ""
    Write-Host "  Nach Installation: STPadServer-Dienst starten (Windows-Dienste oder Startmenue signotec)"
    Write-Host ""
    $open = Read-Host "Download-Seiten im Browser oeffnen? (j/n)"
    if ($open -eq "j" -or $open -eq "J" -or $open -eq "y") {
        Start-Process "https://www.signotec.com/portal/seiten/signotec-signopad-api-web-900000546-10002.html"
        Start-Sleep -Milliseconds 800
        Start-Process "https://en.signotec.com/portal/seiten/download-developer-tools-api-sdk--900000510-10002.html"
    }
    if (-not $AfterInstall) {
        Write-Host ""
        Write-Host "Nach Installation erneut ausfuehren:" -ForegroundColor Green
        Write-Host "  .\scripts\get-signotec-lib.ps1 -AfterInstall"
        Write-Host ""
        exit 0
    }
}

Write-Host "Schritt 2 - Datei auf diesem PC suchen..." -ForegroundColor Yellow
$source = Find-SignotecLib
if (-not $source) {
    Write-Host "  Nicht in Program Files gefunden. Versuche laufenden STPadServer (Port 49494)..." -ForegroundColor Yellow
    $live = Test-PadServerRunning
    if ($live.Ok) {
        New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null
        Set-Content -Path $Dest -Value $live.Content -Encoding UTF8
        Write-Host "  OK: von $($live.Url) nach $Dest" -ForegroundColor Green
        $source = $Dest
    }
}

if (-not $source) {
    Write-Host ""
    Write-Host "FEHLER: STPadServerLib.js noch nicht verfuegbar." -ForegroundColor Red
    Write-Host ""
    Write-Host "Pruefen Sie:" -ForegroundColor Yellow
    Write-Host "  1. signoPAD-API/Web installiert?"
    Write-Host "  2. Dienst STPadServer laeuft? (services.msc -> signotec)"
    Write-Host "  3. Browser-Test: https://localhost:49494 (Zertifikat bestaetigen)"
    Write-Host ""
    Write-Host "Support Signotec (schnellere Anfrage):" -ForegroundColor Cyan
    Write-Host "  E-Mail: info@signotec.com"
    Write-Host "  Betreff: signoPAD-API/Web Windows Download fuer Integration"
    Write-Host "  Text: Wir nutzen signotec Pad + BauPass Web-App, bitte Download-Link signoPAD-API/Web 3.5.0"
    exit 1
}

if ($source -ne $Dest) {
    New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null
    Copy-Item -Path $source -Destination $Dest -Force
}
$size = (Get-Item $Dest).Length
Write-Host "  OK: $Dest ($size bytes)" -ForegroundColor Green

Write-Host ""
Write-Host "Schritt 3 - BauPass deploy (optional)..." -ForegroundColor Yellow
if ($Deploy) {
    & "$Root\deploy\railway-up.ps1"
} else {
    Write-Host "  Fuer Server:  .\deploy\railway-up.ps1   (nach railway login)"
    Write-Host "  Oder:         npm run vendor:signotec:install -Deploy"
}

Write-Host ""
Write-Host "Fertig. Browser: Strg+Shift+R, dann Signotec Pad testen." -ForegroundColor Green
