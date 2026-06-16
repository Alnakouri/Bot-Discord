@echo off
title MALENA - La Gitana
color 0D
echo ============================================================
echo      MALENA - INITIALISATION (Marseille Connection)
echo ============================================================

cd /d "%~dp0"

echo 🔐 Verification de l'environnement securise...
if not exist ".env.encrypted" (
    echo ⚠️  Fichier crypte introuvable !
    echo 🛠️  Lancement du cryptage initial...
    python secure_env.py
)

echo.
echo 💃 Lancement de Malena...
python bot_malena.py
pause
