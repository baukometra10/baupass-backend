@echo off
cd /d "%~dp0.."
echo.
echo === BauPass Deploy ohne Token ===
echo.
echo Schritt 1: Browser oeffnet sich - bitte bei Railway einloggen
railway login
if errorlevel 1 goto fehler
echo.
echo Schritt 2: Waehlen Sie: Workspace -^> baupass-control -^> Service web
railway link
if errorlevel 1 goto fehler
echo.
echo Schritt 3: Code wird hochgeladen (2-8 Minuten)...
railway up --detach
if errorlevel 1 goto fehler
echo.
echo Fertig. Pruefen Sie:
echo   https://baupass-production.up.railway.app/api/health
echo   https://baupass-production.up.railway.app/worker-build.json
pause
exit /b 0
:fehler
echo.
echo FEHLER. Lesen Sie: deploy\WELCHE-NUMMER-IST-WAS.md
pause
exit /b 1
