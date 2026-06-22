$files = @(
  'index.html','app.js','embed-helpers.js','control-sw.js',
  'admin-v2/index.html','admin-v2/app.js','admin-v2/contracts.html','admin-v2/chat.html',
  'admin-v2/i18n-strings.js','admin-v2/i18n-strings-de.js',
  'enterprise-hub.html','enterprise-hub-i18n.js',
  'foreman.html','contract-sign.html','ai-command-center.html','worker-app.js',
  'backend/server.py','backend/app/platform/ai/intents.py'
)
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
  @('BauPass-Admin-Panel','WorkPass-Admin-Panel'),
  @('im BauPass','in WorkPass'),
  @('to BauPass','to WorkPass'),
  @('in BauPass','in WorkPass'),
  @('BauPass mit','WorkPass mit'),
  @('reload BauPass','reload WorkPass'),
  @('BauPass Telefon','WorkPass Telefon'),
  @('BauPass Mitarbeiter','WorkPass Mitarbeiter'),
  @('BauPass Operations','WorkPass Operations'),
  @('BauPass Bericht','WorkPass Bericht'),
  @('BauPass DATEV','WorkPass DATEV'),
  @('BauPass-Betriebsbericht','WorkPass-Betriebsbericht'),
  @('Baukometra','Suppix Technologie UG'),
  @('BauKometra','Suppix Technologie UG'),
  @('baukometra-logo.svg','suppix-ai-logo.svg'),
  @('baukometra-alt-logo.svg','suppix-ai-logo.svg'),
  @('>BauPass<','>WorkPass<'),
  @('BauPass','WorkPass')
)
foreach ($f in $files) {
  if (-not (Test-Path $f)) { Write-Host "SKIP $f"; continue }
  $c = Get-Content $f -Raw -Encoding UTF8
  $orig = $c
  foreach ($pair in $replacements) {
    $c = $c.Replace($pair[0], $pair[1])
  }
  if ($c -ne $orig) {
    Set-Content -Path $f -Value $c -Encoding UTF8 -NoNewline
    Write-Host "UPDATED $f"
  } else {
    Write-Host "unchanged $f"
  }
}
