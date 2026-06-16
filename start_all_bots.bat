@echo off
title Launcher TES Bots - Tous les Bots
color 0A

echo ========================================
echo    LANCEMENT DE TOUS LES BOTS
echo    Sheogorath, M'aiq, Alfred, Za'ji, Johnny, Malena
echo ========================================
echo.

REM Sheogorath (Prince de la Folie)
echo [1/5] Demarrage de Sheogorath...
start /min "Sheogorath Bot" cmd /k "cd /d "%~dp0Sheogorath" && python bot_sheogorath.py"
timeout /t 3 /nobreak >nul

REM M'aiq le Menteur
echo [2/5] Demarrage de M'aiq le Menteur...
start /min "M'aiq Bot" cmd /k "cd /d "%~dp0MaiqBot" && python bot_maiq.py"
timeout /t 3 /nobreak >nul

REM Alfred Pennyworth
echo [3/5] Demarrage d'Alfred...
start /min "Alfred Bot" cmd /k "cd /d "%~dp0Alfred" && python bot_alfred.py"
timeout /t 3 /nobreak >nul

REM Za'ji le Capitaine
echo [4/5] Demarrage de Za'ji le Capitaine...
start /min "Za'ji Bot" cmd /k "cd /d "%~dp0ZajiBot" && python bot_zaji.py"
timeout /t 3 /nobreak >nul

REM Johnny Silverbot
echo [5/6] Demarrage de Johnny Silverbot...
start /min "Johnny Bot" cmd /k "cd /d "%~dp0JohnnyBot" && python bot_johnny.py"
timeout /t 2 /nobreak >nul

REM Malena (La Gitana)
echo [6/6] Demarrage de Malena...
start /min "Malena Bot" cmd /k "color 0D && cd /d "%~dp0MalenaBot" && python bot_malena.py"
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo  SUCCES ! Les 6 bots sont en cours de lancement.
echo ========================================

echo.
echo ========================================
echo  Lancer le Dashboard Unifie ? (O/N)
echo ========================================
set /p dashboard="Votre choix: "
if /i "%dashboard%"=="O" (
    start /min "Dashboard" cmd /k "cd /d "%~dp0dashboard" && start_dashboard.bat"
    echo Dashboard lance sur http://localhost:8501
)

echo.
echo  (Gardez les fenetres consolles ouvertes pour les logs bruts)
pause
