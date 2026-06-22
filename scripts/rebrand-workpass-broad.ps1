$files = Get-ChildItem -Recurse -File -Include *.html,*.js,*.css,*.json,*.py |
  Where-Object {
    $p = $_.FullName
    $p -notmatch '\\node_modules\\|\\\.venv|\\mobile\\build\\|\\\.git\\|\\test-results\\|server-err\.txt'
  } |
  Select-Object -ExpandProperty FullName

$replacements = @(
  @('BauPass KI','SUPPIX AI'),
  @('BauPass AI','SUPPIX AI'),
  @('Control Pass KI','SUPPIX AI'),
  @('Control Pass AI','SUPPIX AI'),
  @('Control Pass','WorkPass'),
  @('BauPass Control','WorkPass'),
  @('Enterprise BauPass','Enterprise WorkPass'),
  @('BauPass Plattform','WorkPass Plattform'),
  @('BauPass-Admin','WorkPass-Admin'),
  @('Baukometra','Suppix Technologie UG'),
  @('BauKometra','Suppix Technologie UG'),
  @('baukometra-logo.svg','suppix-ai-logo.svg'),
  @('baukometra-alt-logo.svg','suppix-ai-logo.svg'),
  @('BauPass','WorkPass')
)

$skipPatterns = @(
  'baupass_client\.py$',
  'rebrand-workpass\.ps1$',
  '\\uploads\\',
  '\\branding\\baukometra'
)

foreach ($f in $files) {
  $skip = $false
  foreach ($sp in $skipPatterns) {
    if ($f -match $sp) { $skip = $true; break }
  }
  if ($skip) { continue }

  try {
    $c = Get-Content $f -Raw -Encoding UTF8 -ErrorAction Stop
  } catch {
    continue
  }
  if ($null -eq $c -or $c.Length -eq 0) { continue }

  $orig = $c
  foreach ($pair in $replacements) {
    $c = $c.Replace($pair[0], $pair[1])
  }
  if ($c -ne $orig) {
    Set-Content -Path $f -Value $c -Encoding UTF8 -NoNewline
    Write-Host "UPDATED $f"
  }
}
