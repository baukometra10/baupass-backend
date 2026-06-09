# BauPass Signotec Bridge — one-time setup per Windows PC (signoPAD-API/Web 3.5.0)
# {{BASE_URL}} is replaced when served from BauPass API.
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$BaseUrl = '{{BASE_URL}}'
$InstallerName = 'signotec_signoPAD-API_Web_3.5.0.exe'
$Port = 49494

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Admin {
    if (Test-Admin) { return }
    Write-Host 'BauPass: Administratorrechte werden angefordert...' -ForegroundColor Yellow
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($SkipInstall) { $arg += ' -SkipInstall' }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $arg
    exit 0
}

function Get-STPadServerExe {
    $paths = @(
        "${env:ProgramFiles(x86)}\signotec\signoPAD-API Web\STPadServer.exe",
        "$env:ProgramFiles\signotec\signoPAD-API Web\STPadServer.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Start-SignotecBridge {
    foreach ($name in @('STPadServer', 'signotec STPadServer', 'signotec WebSocket Pad Server')) {
        $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
        if ($svc) {
            if ($svc.Status -ne 'Running') {
                Write-Host "BauPass: starte Dienst $name..." -ForegroundColor Cyan
                Start-Service $name
            }
            return $true
        }
    }
    $exe = Get-STPadServerExe
    if ($exe) {
        $running = Get-Process STPadServer -ErrorAction SilentlyContinue
        if (-not $running) {
            Write-Host "BauPass: starte STPadServer.exe $Port..." -ForegroundColor Cyan
            Start-Process -FilePath $exe -ArgumentList "$Port" -WindowStyle Hidden
        }
        return $true
    }
    return $false
}

function Test-SignotecPort {
    try {
        return (Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded
    } catch {
        return $false
    }
}

function Wait-SignotecPort {
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-SignotecPort) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

Ensure-Admin

if (-not $SkipInstall) {
    $installerUrl = "$BaseUrl/api/signotec/installer"
    $dest = Join-Path $env:TEMP $InstallerName
    Write-Host 'BauPass: lade Signotec-Bridge vom Server...' -ForegroundColor Cyan
    Invoke-WebRequest -Uri $installerUrl -OutFile $dest -UseBasicParsing
    Write-Host 'BauPass: Installation (einmal pro PC)...' -ForegroundColor Cyan
    $installArgs = '/s /v"/qn ADDLOCAL=WebSocketPadServer,PadDrivers CERT_SEL=\"Localhost\" ALLOW_EDGE_LOOPBACK=\"Yes\""'
    $proc = Start-Process -FilePath $dest -ArgumentList $installArgs -Wait -PassThru
    if ($proc.ExitCode -ne 0 -and $proc.ExitCode -ne 3010) {
        Write-Host "Hinweis: Installer ExitCode $($proc.ExitCode) — pruefe ob signotec installiert ist." -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 3
}

if (-not (Start-SignotecBridge)) {
    Write-Host 'FEHLER: STPadServer nicht gefunden. Installation erneut ausfuehren.' -ForegroundColor Red
    pause
    exit 1
}

Write-Host "BauPass: warte auf Port $Port..." -ForegroundColor Cyan
if (-not (Wait-SignotecPort)) {
    Write-Host "FEHLER: Port $Port antwortet nicht. Windows-Firewall oder STPadServer pruefen." -ForegroundColor Red
    pause
    exit 1
}

Write-Host 'BauPass: Bridge laeuft. Browser oeffnet fuer Zertifikat (Firefox: Erweitert -> Risiko akzeptieren).' -ForegroundColor Green
Start-Process "https://127.0.0.1:$Port/"
Write-Host 'Fertig. BauPass neu laden (Strg+Shift+R) und Signaturgeraet testen.' -ForegroundColor Green
pause
