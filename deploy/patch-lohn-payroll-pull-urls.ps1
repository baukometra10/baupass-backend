# Re-apply WorkPass Lohn pull-URL patch on Railway service workpass-Lohn.
# Survives only until the next Lohn image redeploy from its own Git repo —
# then run this again (or merge the same change into the Lohn source).
#
# Usage (from repo root, Railway CLI linked to project):
#   .\deploy\patch-lohn-payroll-pull-urls.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "deploy\patch-lohn-payroll-pull-urls.mjs"))) {
  $Root = $PSScriptRoot
}
$Script = Join-Path $Root "deploy\patch-lohn-payroll-pull-urls.mjs"
if (-not (Test-Path $Script)) {
  throw "Missing $Script"
}

Write-Host "Applying Lohn payroll pull URL patch via railway ssh -s workpass-Lohn ..."
Get-Content -Raw -Path $Script | railway ssh -s workpass-Lohn -- "cat > /tmp/patch-lohn-payroll-pull-urls.mjs && node /tmp/patch-lohn-payroll-pull-urls.mjs && rm -f /tmp/patch-lohn-payroll-pull-urls.mjs"
Write-Host "Verify:"
railway ssh -s workpass-Lohn -- "grep -n 'NEVER /api/contracts\|payroll-batch\|api/contracts' server/month-close.mjs | head -20"
