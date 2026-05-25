# Code zu GitHub pushen (Konto baukometra10).
# Vorher: https://github.com/settings/tokens → Token mit "repo" anlegen.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$RemoteUrl = "https://github.com/baukometra10/baupass-backend.git"
$CurrentRemote = (git remote get-url origin 2>$null)

if ($CurrentRemote -ne $RemoteUrl) {
    Write-Host "Setze origin auf $RemoteUrl" -ForegroundColor Yellow
    git remote set-url origin $RemoteUrl
}

Write-Host "Entferne gespeicherte GitHub-Anmeldung (alter User baupass)..." -ForegroundColor Cyan
cmdkey /delete:LegacyGeneric:target=git:https://github.com 2>$null
cmdkey /delete:git:https://github.com 2>$null

Write-Host ""
Write-Host "Starte git push..." -ForegroundColor Cyan
Write-Host "Login: Benutzer = baukometra10 | Passwort = Personal Access Token (nicht Kontopasswort)" -ForegroundColor Yellow
Write-Host ""

git ls-remote origin 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "GitHub-Repo nicht erreichbar (404 oder kein Zugriff)." -ForegroundColor Red
    Write-Host ""
    Write-Host "Repo zuerst anlegen (als baukometra10 eingeloggt):"
    Write-Host "  https://github.com/new"
    Write-Host "  Name: baupass-backend"
    Write-Host "  OHNE README, .gitignore oder License (Projekt ist schon lokal fertig)"
    Write-Host "  Dann dieses Skript erneut ausfuehren."
    Write-Host ""
}

git push -u origin main 2>&1 | Tee-Object -Variable pushOut
if ($LASTEXITCODE -ne 0) {
    $pushText = ($pushOut | Out-String)
    if ($pushText -match "fetch first|rejected") {
        Write-Host ""
        Write-Host "GitHub hat nur 'Initial commit' – lade volles Projekt hoch..." -ForegroundColor Yellow
        git push --force-with-lease origin main
        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Host "OK – volles Projekt ist auf GitHub." -ForegroundColor Green
            Write-Host "Pruefen: https://github.com/baukometra10/baupass-backend"
            exit 0
        }
    }
    $err = $pushText
    if ($err -match "denied to baupass") {
        Write-Host ""
        Write-Host "Falscher GitHub-User: baupass (alt). Bitte als baukometra10 anmelden." -ForegroundColor Red
        Write-Host "Windows: Einstellungen -> Konten -> Anmeldeinfo -> Windows-Anmeldeinformationen"
        Write-Host "  -> git:https://github.com entfernen, dann Skript erneut starten."
    }
    Write-Host ""
    Write-Host "Push fehlgeschlagen." -ForegroundColor Red
    Write-Host "1. Token: https://github.com/settings/tokens (Berechtigung: repo)"
    Write-Host "2. Login-User: baukometra10"
    Write-Host "3. Erneut: .\deploy\github-push.ps1"
    exit $LASTEXITCODE
}

# GitHub hat oft nur "Initial commit" – volles Projekt ersetzt das sicher.
$localHead = (git rev-parse main).Trim()
$remoteHead = (git rev-parse origin/main 2>$null).Trim()
if ($localHead -ne $remoteHead) {
    Write-Host ""
    Write-Host "Remote hat anderen Stand (z.B. nur Initial commit). Ersetze mit vollem Projekt..." -ForegroundColor Yellow
    git push --force-with-lease origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Force-Push fehlgeschlagen. Nochmal mit baukometra10-Token versuchen." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "OK – Code ist auf GitHub." -ForegroundColor Green
Write-Host "Naechster Schritt: Railway mit Repo verbinden (siehe docs/github-railway.md)"
