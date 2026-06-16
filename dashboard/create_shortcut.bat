@echo off
setlocal EnableDelayedExpansion
REM ============================================
REM  Creation du raccourci Bureau - Dashboard
REM ============================================

set SHORTCUT_NAME=Dashboard Bots Discord
set DESKTOP=%USERPROFILE%\Desktop
set SCRIPT_DIR=%~dp0

REM Creer le raccourci via PowerShell (methode native Windows)
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $sc = $ws.CreateShortcut('%DESKTOP%\%SHORTCUT_NAME%.lnk'); ^
   $sc.TargetPath = '%SCRIPT_DIR%start_dashboard.bat'; ^
   $sc.WorkingDirectory = '%SCRIPT_DIR%'; ^
   $sc.Description = 'Dashboard unifie des 6 bots Discord'; ^
   $sc.IconLocation = 'shell32.dll,21'; ^
   $sc.Save()"

echo.
echo [OK] Raccourci cree sur le Bureau : "%SHORTCUT_NAME%"
echo      Double-cliquez dessus pour lancer le dashboard.
