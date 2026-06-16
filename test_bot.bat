@echo off
REM ======================================================================
REM SCRIPT DE DÉMARRAGE RAPIDE - TEST LOCAL
REM ======================================================================
REM Permet de tester un bot rapidement en local

echo.
echo ===============================================
echo   TEST RAPIDE DES BOTS DISCORD
echo ===============================================
echo.
echo Quel bot voulez-vous tester ?
echo.
echo [1] Sheogorath (Le Prince de la Folie)
echo [2] M'aiq (Le Menteur)
echo [3] Alfred (Le Majordome)
echo [4] TOUS les bots (en parallèle)
echo [5] Vérifier la configuration (check_deployment_ready.py)
echo [0] Quitter
echo.

set /p choice="Votre choix (0-5): "

if "%choice%"=="1" goto sheogorath
if "%choice%"=="2" goto maiq
if "%choice%"=="3" goto alfred
if "%choice%"=="4" goto all
if "%choice%"=="5" goto check
if "%choice%"=="0" goto end
goto invalid

:sheogorath
echo.
echo [SHEOGORATH] Démarrage...
cd Sheogorath
python bot_sheogorath.py
goto end

:maiq
echo.
echo [M'AIQ] Démarrage...
cd MaiqBot
python bot_maiq.py
goto end

:alfred
echo.
echo [ALFRED] Démarrage...
cd Alfred
python bot_alfred.py
goto end

:all
echo.
echo [TOUS] Démarrage des 3 bots en parallèle...
echo Ouvrez les fenêtres de logs pour chaque bot
echo.
start "Sheogorath Bot" cmd /k "cd Sheogorath && python bot_sheogorath.py"
timeout /t 2 /nobreak >nul
start "M'aiq Bot" cmd /k "cd MaiqBot && python bot_maiq.py"
timeout /t 2 /nobreak >nul
start "Alfred Bot" cmd /k "cd Alfred && python bot_alfred.py"
echo.
echo Les 3 bots sont lancés dans des fenêtres séparées.
echo Fermez les fenêtres pour arrêter les bots.
goto end

:check
echo.
echo [VÉRIFICATION] Configuration des bots...
python check_deployment_ready.py
pause
goto end

:invalid
echo.
echo Choix invalide ! Veuillez choisir entre 0 et 5.
timeout /t 2 /nobreak >nul
goto start

:end
echo.
echo Terminé.
pause
