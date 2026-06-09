# Run on the PC where Signotec ALREADY WORKS — copies installer + start script to USB.
param(
    [string]$UsbDrive = ""
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$InstallerName = 'signotec_signoPAD-API_Web_3.5.0.exe'
$StartBat = Join-Path $Root 'vendor\signotec\baupass-stpadserver-start.bat'
$SetupHtml = Join-Path $Root 'signotec-pc2-setup.html'

if (-not $UsbDrive) {
    $UsbDrive = (Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -eq 2 } | Select-Object -First 1).DeviceID
}
if (-not $UsbDrive) {
    Write-Host 'Kein USB-Laufwerk gefunden. Bitte -UsbDrive E: angeben.' -ForegroundColor Red
    exit 1
}

$destDir = Join-Path $UsbDrive 'BauPass-Signotec-PC2'
New-Item -ItemType Directory -Path $destDir -Force | Out-Null

$localInstaller = Join-Path $Root "vendor\signotec\$InstallerName"
if (Test-Path $localInstaller) {
    Copy-Item $localInstaller (Join-Path $destDir $InstallerName) -Force
} else {
    Write-Host "Lade Installer nach $destDir ..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri 'https://baupass-control.up.railway.app/api/signotec/installer' -OutFile (Join-Path $destDir $InstallerName) -UseBasicParsing
}

Copy-Item $StartBat (Join-Path $destDir 'baupass-stpadserver-start.bat') -Force
if (Test-Path $SetupHtml) {
    Copy-Item $SetupHtml (Join-Path $destDir 'ANLEITUNG-signotec-pc2.html') -Force
}

@"
BauPass Signotec — PC 2 Einrichtung
===================================
1) signotec_signoPAD-API_Web_3.5.0.exe doppelklicken (Localhost waehlen)
2) baupass-stpadserver-start.bat doppelklicken
3) Firefox: https://localhost:49494 Zertifikat bestaetigen
4) BauPass Strg+Shift+R

Login in BauPass (Admin/Firma) ist NICHT relevant.
"@ | Set-Content -Path (Join-Path $destDir 'LESEN.txt') -Encoding UTF8

Write-Host "Fertig: $destDir" -ForegroundColor Green
Write-Host 'USB an PC 2 stecken und LESEN.txt folgen.' -ForegroundColor Green
