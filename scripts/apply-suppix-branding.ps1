$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$iconPairs = @(
  @("/worker-icon-192-20260511f.png", "/branding/suppix-icon-192.png"),
  @("/worker-icon-512-20260511f.png", "/branding/suppix-icon-512.png"),
  @("/worker-icon-192.png", "/branding/suppix-icon-192.png"),
  @("/worker-icon-512.png", "/branding/suppix-icon-512.png"),
  @("./worker-icon-192.png", "./branding/suppix-icon-192.png"),
  @("./worker-icon-512.png", "./branding/suppix-icon-512.png"),
  @("/worker-icon-192.svg", "/branding/suppix-ai-mark.svg"),
  @("/worker-icon-512.svg", "/branding/suppix-ai-mark.svg"),
  @("./worker-icon-192.svg", "./branding/suppix-ai-mark.svg"),
  @("./worker-icon-512.svg", "./branding/suppix-ai-mark.svg")
)
$textPairs = @(
  @("WorkPass", "SUPPIX")
)
$skip = [regex]"\\node_modules\\|\\mobile\\|\\backend\\|\\vendor\\|\\\.git\\|translation-cache|missing-keys|i18n-extra-draft|emp-app\.tmp|deploy\\grafana"

Get-ChildItem -Recurse -File -Include *.html,*.js,*.json,*.css |
  Where-Object { -not $skip.IsMatch($_.FullName) } |
  ForEach-Object {
    $content = Get-Content $_.FullName -Raw -Encoding UTF8
    $original = $content
    foreach ($pair in $iconPairs) { $content = $content.Replace($pair[0], $pair[1]) }
    foreach ($pair in $textPairs) { $content = $content.Replace($pair[0], $pair[1]) }
    if ($content -ne $original) {
      Set-Content -Path $_.FullName -Value $content -Encoding UTF8 -NoNewline
      Write-Host $_.FullName
    }
  }

Write-Host "Done."
