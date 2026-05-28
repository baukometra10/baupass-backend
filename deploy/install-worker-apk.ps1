# Install BauPass worker APK on a connected Android test device via adb.
# Usage:
#   .\deploy\install-worker-apk.ps1 -ApkPath "$env:USERPROFILE\Downloads\app-release.apk"
#   .\deploy\install-worker-apk.ps1 -DownloadLatest   # requires GitHub CLI (gh)
param(
    [Parameter(ParameterSetName = "Path")]
    [string] $ApkPath = "",

    [Parameter(ParameterSetName = "Download")]
    [switch] $DownloadLatest,

    [string] $Repo = "baukometra10/baupass-backend",
    [string] $Workflow = "flutter-worker-apk.yml",
    [string] $ArtifactName = "baupass-worker-apk"
)

$ErrorActionPreference = "Stop"

function Resolve-Adb {
    $adb = Get-Command adb -ErrorAction SilentlyContinue
    if ($adb) { return $adb.Source }
    $fallback = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
    if (Test-Path $fallback) { return $fallback }
    throw "adb nicht gefunden. Platform Tools installieren oder adb in PATH legen."
}

function Get-LatestApkFromGh {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw "GitHub CLI (gh) fehlt. APK manuell aus Actions herunterladen oder -ApkPath nutzen."
    }
    $runId = gh run list --repo $Repo --workflow $Workflow --limit 1 --json databaseId,conclusion --jq '.[0].databaseId'
    if (-not $runId) { throw "Kein Workflow-Run gefunden." }
    $dest = Join-Path $env:TEMP "baupass-worker-apk-$runId"
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
    New-Item -ItemType Directory -Path $dest | Out-Null
    Push-Location $dest
    try {
        gh run download $runId --repo $Repo --name $ArtifactName
    } finally {
        Pop-Location
    }
    $apk = Get-ChildItem -Path $dest -Filter "*.apk" -Recurse | Select-Object -First 1
    if (-not $apk) { throw "Keine APK im Artifact $ArtifactName." }
    return $apk.FullName
}

if ($DownloadLatest) {
    $ApkPath = Get-LatestApkFromGh
    Write-Host "APK aus GitHub Actions: $ApkPath" -ForegroundColor Cyan
}

if (-not $ApkPath -or -not (Test-Path $ApkPath)) {
    Write-Host "APK nicht gefunden. Beispiel:" -ForegroundColor Yellow
    Write-Host '  .\deploy\install-worker-apk.ps1 -ApkPath "$env:USERPROFILE\Downloads\app-release.apk"'
    Write-Host "  .\deploy\install-worker-apk.ps1 -DownloadLatest"
    exit 1
}

$adbExe = Resolve-Adb
Write-Host "adb: $adbExe" -ForegroundColor DarkGray

& $adbExe devices
$devices = & $adbExe devices | Select-String "device$" | Where-Object { $_ -notmatch "List of devices" }
if (-not $devices) {
    throw "Kein Android-Geraet verbunden. USB-Debugging aktivieren und adb devices pruefen."
}

Write-Host "Installiere $ApkPath ..." -ForegroundColor Cyan
& $adbExe install -r $ApkPath
if ($LASTEXITCODE -ne 0) {
    throw "adb install fehlgeschlagen (Exit $LASTEXITCODE)."
}

Write-Host "OK — BauPass Worker installiert. NFC am Geraet aktivieren, dann App oeffnen." -ForegroundColor Green
