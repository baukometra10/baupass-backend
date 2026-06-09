# BauPass — check Signotec STPadServer on this PC (no install).
$Port = 49494
Write-Host '=== BauPass Signotec Check ===' -ForegroundColor Cyan
$exe = $null
foreach ($p in @(
    "${env:ProgramFiles(x86)}\signotec\signoPAD-API Web\STPadServer.exe",
    "$env:ProgramFiles\signotec\signoPAD-API Web\STPadServer.exe"
)) {
    if (Test-Path $p) { $exe = $p; break }
}
if ($exe) {
    Write-Host "Installiert: $exe" -ForegroundColor Green
} else {
    Write-Host 'NICHT installiert — baupass-signotec-setup.bat als Admin ausfuehren.' -ForegroundColor Red
}
$proc = Get-Process STPadServer -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "STPadServer laeuft (PID $($proc.Id -join ', '))" -ForegroundColor Green
} else {
    Write-Host 'STPadServer laeuft NICHT — Bridge starten.bat ausfuehren.' -ForegroundColor Red
}
try {
    $ok = (Test-NetConnection -ComputerName localhost -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded
    if ($ok) {
        Write-Host "Port $Port: OFFEN — oeffne https://localhost:$Port im Browser" -ForegroundColor Green
    } else {
        Write-Host "Port $Port: GESCHLOSSEN" -ForegroundColor Red
    }
} catch {
    Write-Host "Port-Test fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Red
}
pause
