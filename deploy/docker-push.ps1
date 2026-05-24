# Build BauPass Docker image and push to Docker Hub (no GitHub required).
param(
    [string]$DockerUser = $env:DOCKERHUB_USER,
    [string]$Tag = "latest"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker fehlt. Installieren: https://www.docker.com/products/docker-desktop/" -ForegroundColor Red
    exit 1
}

if (-not $DockerUser) {
    $DockerUser = Read-Host "Docker Hub Benutzername (z.B. meinname von hub.docker.com/u/meinname)"
}
$DockerUser = $DockerUser.Trim()
if (-not $DockerUser) {
    Write-Host "Benutzername erforderlich." -ForegroundColor Red
    exit 1
}

$Image = "${DockerUser}/baupass:${Tag}"
Write-Host "Baue Image: $Image" -ForegroundColor Cyan
docker build -t $Image .

Write-Host ""
Write-Host "Docker Hub Login (E-Mail + Passwort oder Access Token)..." -ForegroundColor Yellow
docker login
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Push: $Image" -ForegroundColor Cyan
docker push $Image
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Fertig. In Railway eintragen:" -ForegroundColor Green
Write-Host "  Image: $Image"
Write-Host "  Settings -> Source -> Docker Image -> Deploy"
Write-Host ""
Write-Host "Variablen: PUBLIC_BASE_URL=https://baupass-control.up.railway.app"
