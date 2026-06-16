FROM python:3.11-slim

WORKDIR /app

# Dépendances système (ffmpeg audio, libsodium pour discord voice)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsodium-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du dossier partagé
COPY shared/ ./shared/

# Configuration d'environnement via variable
ENV DATA_DIR="/app/data"

# La commande finale et le code bot_*.py seront montés dynamiquement par docker-compose
