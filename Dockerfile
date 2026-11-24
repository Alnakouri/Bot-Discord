# Version de Python FIGEE, comme les paquets (requirements.lock) : deux builds a des mois
# d'ecart doivent donner la meme image. Mise a jour : docs/MAINTENANCE.md.
FROM python:3.11.18-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dépendances système (ffmpeg audio, libsodium pour discord voice)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsodium-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python : les versions EXACTES de requirements.lock, jamais « la derniere ».
# Mesure du 2026-11-24 : LAYA ne se construisait plus (laya 0.5 sortie le 19/11 avait
# retire `laya.agent`), et des images de juin tournaient sans Pillow. Une image
# reconstruite doit etre celle qu'on a testee, pas celle du jour.
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

# Copie du dossier partagé
COPY shared/ ./shared/

# Configuration d'environnement via variable
ENV DATA_DIR="/app/data"

# Utilisateur non-root (sécurité : ne pas tourner en root dans le conteneur).
# Les points de montage data/logs sont créés et possédés par botuser ; sur
# Docker Desktop (Windows) les bind mounts restent inscriptibles quel que soit l'UID.
RUN useradd --create-home --uid 10001 botuser \
    && mkdir -p /app/data /app/bot/logs \
    && chown -R botuser:botuser /app
USER botuser

# La commande finale et le code bot_*.py seront montés dynamiquement par docker-compose
