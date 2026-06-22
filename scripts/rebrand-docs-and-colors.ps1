$replacements = @(
  @('#0f4c5c','#06b6d4'),
  @('#e36414','#a855f7'),
  @('BauPass KI','SUPPIX AI'),
  @('BauPass AI','SUPPIX AI'),
  @('Control Pass KI','SUPPIX AI'),
  @('Control Pass AI','SUPPIX AI'),
  @('Control Pass','WorkPass'),
  @('BauPass Control','WorkPass'),
  @('Baukometra','Suppix Technologie UG'),
  @('BauKometra','Suppix Technologie UG'),
  @('BauPass','WorkPass')
)
$roots = @('docs','vendor','deploy','admin-v2','android-hce-companion','backend')
foreach ($root in $roots) {
  $base = Join-Path (Get-Location) $root
  if (-not (Test-Path $base)) { continue }
  Get-ChildItem -Recurse -File $base -Include *.md,*.html,*.xml,*.yaml,*.py,*.json,*.css,*.js |
    Where-Object { $_.FullName -notmatch '\\node_modules\\|\\\.venv|\\build\\|rebrand-|update-brand' } |
    ForEach-Object {
      $c = Get-Content $_.FullName -Raw -Encoding UTF8
      $orig = $c
      foreach ($pair in $replacements) { $c = $c.Replace($pair[0], $pair[1]) }
      if ($c -ne $orig) {
        Set-Content -Path $_.FullName -Value $c -Encoding UTF8 -NoNewline
        Write-Host $_.FullName
      }
    }
}
