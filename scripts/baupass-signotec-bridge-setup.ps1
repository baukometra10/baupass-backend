# BauPass Signotec Bridge — one-time setup per Windows PC (signoPAD-API/Web 3.5.0)
# {{BASE_URL}} is replaced when served from BauPass API.
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Continue'
$BaseUrl = '{{BASE_URL}}'
$InstallerName = 'signotec_signoPAD-API_Web_3.5.0.exe'
$Port = 49494
$LogFile = Join-Path ([Environment]::GetFolderPath('Desktop')) 'baupass-signotec-setup.log'

function Write-Log($msg, $color) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    if ($color) { Write-Host $msg -ForegroundColor $color } else { Write-Host $msg }
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Admin {
    if (Test-Admin) { return }
    Write-Log 'BauPass: Administratorrechte werden angefordert...' Yellow
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($SkipInstall) { $arg += ' -SkipInstall' }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $arg
    exit 0
}

function Find-STPadServerExe {
    $candidates = @(
        "${env:ProgramFiles(x86)}\signotec\signoPAD-API Web\STPadServer.exe",
        "$env:ProgramFiles\signotec\signoPAD-API Web\STPadServer.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    $roots = @("${env:ProgramFiles(x86)}\signotec", "$env:ProgramFiles\signotec")
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        try {
            $hit = Get-ChildItem -Path $root -Filter 'STPadServer.exe' -Recurse -Depth 5 -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) { return $hit.FullName }
        } catch { }
    }
    return $null
}

function Ensure-FirewallRule {
    $name = 'BauPass Signotec STPadServer TCP 49494'
    $existing = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
    if ($existing) { return }
    try {
        New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -ErrorAction Stop | Out-Null
        Write-Log 'Firewall-Regel fuer Port 49494 erstellt.' Cyan
    } catch {
        netsh advfirewall firewall add rule name="$name" dir=in action=allow protocol=TCP localport=$Port | Out-Null
        Write-Log 'Firewall-Regel via netsh erstellt.' Cyan
    }
}

function Install-Autostart {
    $exe = Find-STPadServerExe
    if (-not $exe) { return }
    $workDir = Split-Path $exe -Parent
    $startup = [Environment]::GetFolderPath('Startup')
    $bat = Join-Path $startup 'baupass-signotec-stpadserver.bat'
    $content = @"
@echo off
cd /d "$workDir"
start "" "$exe" $Port
"@
    Set-Content -Path $bat -Value $content -Encoding ASCII
    Write-Log "Autostart erstellt: $bat" Green
}

function Stop-STPadServerProcesses {
    Get-Process STPadServer -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Log "Beende alten STPadServer (PID $($_.Id))..." Yellow
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

function Start-SignotecBridge {
    foreach ($name in @('STPadServer', 'signotec STPadServer', 'signotec WebSocket Pad Server')) {
        $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
        if ($svc) {
            if ($svc.Status -ne 'Running') {
                Write-Log "Starte Dienst $name..." Cyan
                Start-Service $name -ErrorAction SilentlyContinue
            }
            if ((Get-Service $name).Status -eq 'Running') { return $true }
        }
    }
    $exe = Find-STPadServerExe
    if (-not $exe) { return $false }
    $workDir = Split-Path $exe -Parent
    Stop-STPadServerProcesses
    Write-Log "Starte STPadServer aus $workDir (Port $Port)..." Cyan
    Start-Process -FilePath $exe -ArgumentList "$Port" -WorkingDirectory $workDir -WindowStyle Hidden
    return $true
}

function Test-SignotecPort {
    try {
        return (Test-NetConnection -ComputerName localhost -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded
    } catch {
        return $false
    }
}

function Wait-SignotecPort {
    for ($i = 0; $i -lt 45; $i++) {
        if (Test-SignotecPort) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

Clear-Content -Path $LogFile -ErrorAction SilentlyContinue
Write-Log '=== BauPass Signotec Setup ===' Cyan
Write-Log "Log: $LogFile"

Ensure-Admin
Ensure-FirewallRule

$existingExe = Find-STPadServerExe
if ($existingExe -and (Test-SignotecPort)) {
    Write-Log 'Signotec bereits installiert und Port 49494 offen.' Green
    Install-Autostart
    Start-Process "https://localhost:$Port/"
    Write-Log 'Fertig. BauPass mit Strg+Shift+R neu laden.' Green
    pause
    exit 0
}

if ($existingExe) {
    Write-Log 'Signotec installiert — starte Bridge...' Cyan
    $SkipInstall = $true
}

if (-not $SkipInstall) {
    $installerUrl = "$BaseUrl/api/signotec/installer"
    $dest = Join-Path $env:TEMP $InstallerName
    Write-Log 'Lade Signotec-Installer vom BauPass-Server...' Cyan
    try {
        Invoke-WebRequest -Uri $installerUrl -OutFile $dest -UseBasicParsing
    } catch {
        Write-Log "FEHLER Download: $($_.Exception.Message)" Red
        pause
        exit 1
    }
    Write-Log '=== WICHTIG: Installations-Assistent ===' Yellow
    Write-Log '1) Alle Schritte mit Weiter/Next bestaetigen' Yellow
    Write-Log '2) Bei Zertifikat-Option: LOCALHOST waehlen (nicht Default!)' Yellow
    Write-Log '3) Installation abschliessen, dann hier weiter' Yellow
    Start-Process -FilePath $dest -Wait
    Start-Sleep -Seconds 4
}

if (-not (Start-SignotecBridge)) {
    Write-Log 'FEHLER: STPadServer.exe nicht gefunden.' Red
    Write-Log 'Bitte signoPAD-API/Web installieren und dieses Skript erneut starten.' Yellow
    pause
    exit 1
}

Write-Log "Warte auf localhost:$Port ..." Cyan
if (-not (Wait-SignotecPort)) {
    Write-Log "FEHLER: Port $Port antwortet nicht." Red
    Write-Log 'Manuell: Windows-Taste -> STPadServer suchen und starten' Yellow
    pause
    exit 1
}

Install-Autostart
Write-Log 'OK: Bridge laeuft auf https://localhost:49494' Green
Write-Log 'Firefox: Erweitert -> Risiko akzeptieren und fortfahren' Green
Start-Process "https://localhost:$Port/"
Write-Log 'Fertig. BauPass mit Strg+Shift+R neu laden.' Green
pause
