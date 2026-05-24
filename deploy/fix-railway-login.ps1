# Einmal ausfuehren: alte Token-Werte loeschen, dann Browser-Login
$ErrorActionPreference = "Continue"
Write-Host "Loesche alte Railway-Token aus dieser PowerShell-Sitzung..." -ForegroundColor Yellow
Remove-Item Env:RAILWAY_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:RAILWAY_API_TOKEN -ErrorAction SilentlyContinue
[System.Environment]::SetEnvironmentVariable("RAILWAY_TOKEN", $null, "User")
[System.Environment]::SetEnvironmentVariable("RAILWAY_API_TOKEN", $null, "User")
railway logout 2>$null
Write-Host ""
Write-Host "OK. Jetzt startet der Browser-Login." -ForegroundColor Green
Write-Host "WICHTIG: Keinen Token mehr einfuegen. Nicht railway whoami mit UUID testen." -ForegroundColor Cyan
Write-Host ""
railway login
