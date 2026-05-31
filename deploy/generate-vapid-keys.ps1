# Generate VAPID keys for PWA Web Push (worker app notifications when closed).
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\deploy\generate-vapid-keys.ps1
#
# Then set in Railway (Service web -> Variables):
#   VAPID_PUBLIC_KEY=<Public Key below>
#   VAPID_PRIVATE_KEY=<Private Key below>
#   VAPID_EMAIL=mailto:ihre-adresse@firma.de
#
# Redeploy or restart the service after saving variables.

$ErrorActionPreference = "Stop"

if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    Write-Host "Node/npx fehlt. Installieren Sie Node.js oder setzen Sie die Keys manuell." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== VAPID Keys (Web Push fuer Mitarbeiter-PWA) ===" -ForegroundColor Cyan
Write-Host ""
npx --yes web-push generate-vapid-keys
Write-Host ""
Write-Host "Kopieren Sie Public + Private Key nach Railway -> Variables." -ForegroundColor Yellow
Write-Host "VAPID_EMAIL z.B.: mailto:admin@baupass.de" -ForegroundColor Yellow
Write-Host ""
Write-Host "Pruefen nach Deploy:" -ForegroundColor Green
Write-Host "  curl https://baupass-production.up.railway.app/api/worker-app/push-vapid-key"
Write-Host "  -> publicKey darf nicht null sein"
Write-Host ""
