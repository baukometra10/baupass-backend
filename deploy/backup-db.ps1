# Manual SQLite backup against a running BauPass instance (superadmin token required).
# Usage:
#   $env:BAUPASS_API_BASE = "https://baupass-production.up.railway.app"
#   $env:BAUPASS_ADMIN_TOKEN = "<session-token>"
#   .\deploy\backup-db.ps1

$base = if ($env:BAUPASS_API_BASE) { $env:BAUPASS_API_BASE.TrimEnd("/") } else { "http://127.0.0.1:8080" }
$token = $env:BAUPASS_ADMIN_TOKEN
if (-not $token) {
  Write-Error "Set BAUPASS_ADMIN_TOKEN to a superadmin session token."
  exit 1
}

$headers = @{
  Authorization = "Bearer $token"
  "Content-Type" = "application/json"
}

$response = Invoke-RestMethod -Uri "$base/api/admin/database/backup" -Method POST -Headers $headers -Body "{}"
Write-Host "Backup OK:" ($response.backupPath ?? $response.path)
