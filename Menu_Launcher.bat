@echo off
setlocal enabledelayedexpansion
title Console de Contrôle - Ecosystème Bots Discord
color 0B

:MENU
cls
echo ========================================================
echo   [     CONSOLE CENTRALE - BOTS DISCORD     ]
echo ========================================================
echo.
echo   [1] Lancer Sheogorath
echo   [2] Lancer M'aiq le Menteur
echo   [3] Lancer Alfred Pennyworth
echo   [4] Lancer Eikichi Onizuka
echo   [5] Lancer Johnny Silverbot
echo   [6] Lancer Malena la Gitana
echo.
echo   [7] ^> LANCER TOUS LES BOTS EN MEME TEMPS
echo.
echo   [8] ^> Lancer le Dashboard d'analyse web (Port 8501)
echo   [Q] ^> Quitter
echo.
echo ========================================================
set /p choix="Quel bot voulez-vous lancer ? (1-8, ou Q) : "

if /i "%choix%"=="1" goto BOOT_SHEO
if /i "%choix%"=="2" goto BOOT_MAIQ
if /i "%choix%"=="3" goto BOOT_ALFRED
if /i "%choix%"=="4" goto BOOT_ONIZUKA
if /i "%choix%"=="5" goto BOOT_JOHNNY
if /i "%choix%"=="6" goto BOOT_MALENA
if /i "%choix%"=="7" goto BOOT_ALL
if /i "%choix%"=="8" goto BOOT_DASHBOARD
if /i "%choix%"=="Q" exit

goto MENU

:BOOT_SHEO
echo Demarrage de Sheogorath...
start /min "Sheogorath Bot" cmd /k "cd /d "%~dp0Sheogorath" && python bot_sheogorath.py"
pause
goto MENU

:BOOT_MAIQ
echo Demarrage de M'aiq...
start /min "M'aiq Bot" cmd /k "cd /d "%~dp0MaiqBot" && python bot_maiq.py"
pause
goto MENU

:BOOT_ALFRED
echo Demarrage d'Alfred...
start /min "Alfred Bot" cmd /k "cd /d "%~dp0Alfred" && python bot_alfred.py"
pause
goto MENU

:BOOT_ONIZUKA
echo Demarrage d'Onizuka...
start /min "Onizuka Bot" cmd /k "cd /d "%~dp0OnizukaBot" && python bot_onizuka.py"
pause
goto MENU

:BOOT_JOHNNY
echo Demarrage de Johnny...
start /min "Johnny Bot" cmd /k "cd /d "%~dp0JohnnyBot" && python bot_johnny.py"
pause
goto MENU

:BOOT_MALENA
echo Demarrage de Malena...
start /min "Malena Bot" cmd /k "cd /d "%~dp0MalenaBot" && python bot_malena.py"
pause
goto MENU

:BOOT_ALL
echo Lancement de tous les bots...
start /min "Sheogorath Bot" cmd /k "cd /d "%~dp0Sheogorath" && python bot_sheogorath.py"
timeout /t 2 /nobreak >nul
start /min "M'aiq Bot" cmd /k "cd /d "%~dp0MaiqBot" && python bot_maiq.py"
timeout /t 2 /nobreak >nul
start /min "Alfred Bot" cmd /k "cd /d "%~dp0Alfred" && python bot_alfred.py"
timeout /t 2 /nobreak >nul
start /min "Onizuka Bot" cmd /k "cd /d "%~dp0OnizukaBot" && python bot_onizuka.py"
timeout /t 2 /nobreak >nul
start /min "Johnny Bot" cmd /k "cd /d "%~dp0JohnnyBot" && python bot_johnny.py"
timeout /t 2 /nobreak >nul
start /min "Malena Bot" cmd /k "cd /d "%~dp0MalenaBot" && python bot_malena.py"
echo Les 6 bots sont lances !
pause
goto MENU

:BOOT_DASHBOARD
echo Demarrage du serveur Dashboard...
start "Dashboard" cmd /k "cd /d "%~dp0dashboard" && start_dashboard.bat"
goto MENU
