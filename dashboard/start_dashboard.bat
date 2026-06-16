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
pause
