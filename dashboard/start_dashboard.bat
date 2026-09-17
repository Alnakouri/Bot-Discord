@echo off
title Dashboard Bots Discord
color 0B
echo ============================================
echo   DASHBOARD UNIFIE - Bots Discord
echo   http://localhost:8501
echo ============================================
echo.
cd /d "%~dp0"
pip install -r backend\requirements.txt --quiet
echo.

REM Raccourci supprimé pour accélération du démarrage

echo.
echo Demarrage du serveur...
timeout /t 2 /nobreak >nul
start http://localhost:8501
python backend\app.py
REM Code 42 = le dashboard s'est arrete pour SE RELANCER (relauncher.py ouvre la
REM nouvelle console). Faire `pause` ici laisserait cette fenetre-ci ouverte sur
REM « appuyez sur une touche » : deux consoles, dont une morte. Dans tous les
REM AUTRES cas — plantage, arret normal — le `pause` reste : c'est lui qui permet
REM de lire l'erreur avant que la fenetre disparaisse.
if "%ERRORLEVEL%"=="42" goto :fin
pause
:fin
