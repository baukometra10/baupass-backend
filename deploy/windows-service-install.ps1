$ErrorActionPreference = "Stop"

param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [string]$PublicBaseUrl = "https://baupass.example.com"
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runScript = Join-Path $projectRoot "backend\entrypoint.py"
$taskName = "BauPassControl"

if (-not (Test-Path $venvPython)) {
    throw "Python aus .venv nicht gefunden: $venvPython"
}

$command = @(
    "$env:HOST='$HostAddress'",
    "$env:PORT='$Port'",
    "$env:PUBLIC_BASE_URL='$PublicBaseUrl'",
    "& '$venvPython' '$runScript' --mode prod"
) -join '; '

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command $command"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force
Start-ScheduledTask -TaskName $taskName
Write-Host "Task $taskName wurde erstellt und gestartet. HOST=$HostAddress PORT=$Port PUBLIC_BASE_URL=$PublicBaseUrl"
