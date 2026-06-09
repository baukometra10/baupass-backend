# Install STPadServerLib.js for BauPass deploy (vendor folder + optional Railway base64).
param(
    [Parameter(Mandatory = $false)]
    [string]$SourcePath,
    [switch]$Deploy,
    [switch]$SkipRailwayEnv
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $Root "vendor\signotec\STPadServerLib.js"
$DestDir = Split-Path -Parent $Dest

function Test-SignotecLib([string]$Path) {
    if (-not (Test-Path $Path)) { return $false }
    $head = Get-Content -Path $Path -TotalCount 40 -ErrorAction SilentlyContinue | Out-String
    return $head -match "STPadServerLibCommons"
}

if (-not $SourcePath) {
  try {
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    $picker = New-Object System.Windows.Forms.OpenFileDialog
    $picker.Filter = "Signotec JS (STPadServerLib.js)|STPadServerLib.js|JavaScript (*.js)|*.js"
    $picker.Title = "STPadServerLib.js aus signoPAD-API/Web waehlen"
    if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
      Write-Host "Abgebrochen." -ForegroundColor Yellow
      exit 1
    }
    $SourcePath = $picker.FileName
  } catch {
    Write-Host "Pfad zu STPadServerLib.js (signoPAD-API/Web):" -ForegroundColor Cyan
    $SourcePath = Read-Host "SourcePath"
    if (-not $SourcePath) { exit 1 }
  }
}

$SourcePath = (Resolve-Path $SourcePath).Path
if (-not (Test-SignotecLib $SourcePath)) {
    Write-Host "Ungueltige Datei - erwartet STPadServerLib.js von signotec signoPAD-API/Web." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
Copy-Item -Path $SourcePath -Destination $Dest -Force
$size = (Get-Item $Dest).Length
Write-Host "OK: $Dest ($size bytes)" -ForegroundColor Green

if (-not $SkipRailwayEnv -and (Get-Command railway -ErrorAction SilentlyContinue)) {
    # Railway env vars are size-limited; use only for smaller libs (< ~20 KB).
    if ($size -le 20000) {
        $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($Dest))
        railway variables set "BAUPASS_SIGNOTEC_LIB_BASE64=$b64"
        Write-Host "Railway: BAUPASS_SIGNOTEC_LIB_BASE64 gesetzt." -ForegroundColor Green
    } else {
        Write-Host "Datei zu gross fuer Railway-Env - wird per Deploy (vendor/signotec/) mitgeliefert." -ForegroundColor Yellow
    }
}

if ($Deploy) {
    & "$Root\deploy\railway-up.ps1"
}

Write-Host ""
Write-Host "Naechste Schritte:" -ForegroundColor Cyan
Write-Host "  1. Deploy:  .\deploy\railway-up.ps1"
Write-Host "  2. Test:    https://baupass-production.up.railway.app/vendor/signotec/STPadServerLib.js"
Write-Host "  3. Browser: Strg+Shift+R, dann Signotec Pad testen."
