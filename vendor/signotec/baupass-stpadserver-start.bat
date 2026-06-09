@echo off
title BauPass - STPadServer starten
set "EXE86=%ProgramFiles(x86)%\signotec\signoPAD-API Web\STPadServer.exe"
set "EXE64=%ProgramFiles%\signotec\signoPAD-API Web\STPadServer.exe"
if exist "%EXE86%" (
  cd /d "%ProgramFiles(x86)%\signotec\signoPAD-API Web"
  start "" "%EXE86%" 49494
  goto opened
)
if exist "%EXE64%" (
  cd /d "%ProgramFiles%\signotec\signoPAD-API Web"
  start "" "%EXE64%" 49494
  goto opened
)
echo Signotec ist NICHT installiert.
echo Bitte zuerst signotec_signoPAD-API_Web_3.5.0.exe installieren.
echo Oeffnen Sie: https://baupass-control.up.railway.app/signotec-pc2-setup.html
pause
exit /b 1
:opened
timeout /t 2 /nobreak >nul
start https://localhost:49494/
echo STPadServer gestartet. Firefox: Zertifikat bestaetigen, dann BauPass neu laden.
pause
