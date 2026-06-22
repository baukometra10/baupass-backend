$files = Get-ChildItem -Recurse -File -Path 'mobile' -Include *.dart,*.xml,*.yaml,*.md |
  Where-Object { $_.FullName -notmatch '\\build\\' }
$replacements = @(
  @('BauPass KI','SUPPIX AI'),
  @('BauPass Assistent (KI)','SUPPIX AI Assistent'),
  @('BauPass Assistent','SUPPIX AI Assistent'),
  @('BauPass Mitarbeiter','WorkPass Mitarbeiter'),
  @('BauPass Worker','WorkPass Worker'),
  @('BauPass Admin','WorkPass Admin'),
  @('in BauPass','in WorkPass'),
  @('BauPass','WorkPass')
)
foreach ($f in $files) {
  $c = Get-Content $f.FullName -Raw -Encoding UTF8
  $orig = $c
  foreach ($pair in $replacements) { $c = $c.Replace($pair[0], $pair[1]) }
  if ($c -ne $orig) {
    Set-Content -Path $f.FullName -Value $c -Encoding UTF8 -NoNewline
    Write-Host $f.FullName
  }
}
