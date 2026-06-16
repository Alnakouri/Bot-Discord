FROM pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime

WORKDIR /app

# Dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Installer Chatterbox TTS + serveur HTTP
RUN pip install --no-cache-dir \
    "transformers<5.0" \
    chatterbox-tts \
    fastapi \
    uvicorn[standard] \
    python-multipart \
    && pip uninstall -y torchvision

# Copier le serveur HTTP
COPY server.py .

# Dossier pour les voix de référence et le cache
RUN mkdir -p /app/voices /app/cache

EXPOSE 5000

CMD ["python", "server.py"]
