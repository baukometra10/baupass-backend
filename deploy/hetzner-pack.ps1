# ZIP fuer Hetzner-Upload (ohne .venv, node_modules, lokale DBs)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$OutZip = Join-Path $Root "baupass-hetzner-upload.zip"

$excludeDirs = @(
    ".git", ".github", ".cursor", ".vscode", ".idea",
    "node_modules", ".venv", ".venv311", "venv",
    "__pycache__", ".pytest_cache", "test-results", "playwright-report",
    "htmlcov", "dist", "build", "desktop", "agent-transcripts"
)
$excludeFiles = @("*.db", "*.sqlite", "*.sqlite3", "*.log", "baupass-hetzner-upload.zip")

if (Test-Path $OutZip) { Remove-Item $OutZip -Force }

$temp = Join-Path $env:TEMP ("baupass-pack-" + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $temp | Out-Null

function Should-Skip([string]$rel) {
    $parts = $rel -split '[\\/]'
    foreach ($d in $excludeDirs) {
        if ($parts -contains $d) { return $true }
    }
    foreach ($pat in $excludeFiles) {
        if ($rel -like $pat) { return $true }
    }
    return $false
}

Get-ChildItem -Path $Root -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($Root.Length + 1)
    if (Should-Skip $rel) { return }
    $dest = Join-Path $temp $rel
    $destDir = Split-Path $dest -Parent
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
    Copy-Item $_.FullName -Destination $dest -Force
}

Compress-Archive -Path (Join-Path $temp '*') -DestinationPath $OutZip -Force
Remove-Item $temp -Recurse -Force

Write-Host "ZIP erstellt:" -ForegroundColor Green
Write-Host "  $OutZip"
Write-Host ""
Write-Host "WinSCP: ZIP nach /opt hochladen, auf dem Server:" -ForegroundColor Cyan
Write-Host "  apt install -y unzip"
Write-Host "  mkdir -p /opt/baupass && unzip -o /opt/baupass-hetzner-upload.zip -d /opt/baupass"
