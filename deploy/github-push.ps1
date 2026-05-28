# Code zu GitHub pushen (Konto baukometra10).
# Vorher: https://github.com/settings/tokens -> Token mit "repo" anlegen.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$RemoteUrl = "https://github.com/baukometra10/baupass-backend.git"
$CurrentRemote = git remote get-url origin 2>$null

if ($CurrentRemote -ne $RemoteUrl) {
    Write-Host "Setze origin auf $RemoteUrl" -ForegroundColor Yellow
    git remote set-url origin $RemoteUrl
}

Write-Host "Entferne gespeicherte GitHub-Anmeldung (alter User baupass)..." -ForegroundColor Cyan
cmdkey /delete:LegacyGeneric:target=git:https://github.com 2>$null
cmdkey /delete:git:https://github.com 2>$null

Write-Host ""
Write-Host "Starte git push..." -ForegroundColor Cyan
Write-Host "Login: Benutzer = baukometra10 | Passwort = Personal Access Token" -ForegroundColor Yellow
Write-Host ""

git ls-remote origin 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "GitHub-Repo nicht erreichbar (404 oder kein Zugriff)." -ForegroundColor Red
    Write-Host "Repo anlegen: https://github.com/new -> Name: baupass-backend" -ForegroundColor Yellow
    Write-Host ""
}

git push -u origin main 2>&1 | Tee-Object -Variable pushOut
if ($LASTEXITCODE -ne 0) {
    $pushText = ($pushOut | Out-String)
    if ($pushText -match "fetch first|rejected") {
        Write-Host ""
        Write-Host "GitHub hat nur Initial commit - lade volles Projekt hoch..." -ForegroundColor Yellow
        git push --force-with-lease origin main
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK - volles Projekt ist auf GitHub." -ForegroundColor Green
            exit 0
        }
    }
    if ($pushText -match "denied to baupass") {
        Write-Host "Falscher GitHub-User. Bitte als baukometra10 anmelden." -ForegroundColor Red
    }
    Write-Host "Push fehlgeschlagen. Token: https://github.com/settings/tokens (repo)" -ForegroundColor Red
    exit $LASTEXITCODE
}

$localHead = (git rev-parse main).Trim()
$remoteHead = (git rev-parse origin/main 2>$null).Trim()
if ($localHead -ne $remoteHead) {
    Write-Host "Remote hat anderen Stand - force-with-lease..." -ForegroundColor Yellow
    git push --force-with-lease origin main
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "OK - Code ist auf GitHub." -ForegroundColor Green
Write-Host "Naechster Schritt: Railway deploy pruefen (docs/github-railway.md)"
