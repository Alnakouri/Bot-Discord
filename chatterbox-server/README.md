# 🔊 Chatterbox TTS (Voice Cloning Server) — PARQUÉ

Ce sous-projet contient le serveur de synthèse vocale (TTS) avec clonage de voix en temps réel basé sur PyTorch et CUDA. Il est conçu pour cloner fidèlement la voix française de Sheogorath (VF officielle de Philippe Bozo).

> [!WARNING]
> **Statut actuel : FEATURE PARKÉE**
> Ce service exigeant un GPU NVIDIA avec pilotes CUDA (`runtime: nvidia`) a été désactivé du fichier d'orchestration global en raison des contraintes d'infrastructure d'hébergement CPU-only.
>
> Pour plus d'informations sur son architecture, ses performances VRAM, sa désactivation et les pistes de réactivation, veuillez vous référer au guide :
> **[FEATURE_VOIX_VISION_GPU.md](../FEATURE_VOIX_VISION_GPU.md)**

## 🗂️ Contenu du Répertoire

- [server.py](server.py) : API web asynchrone sous FastAPI fournissant les routes d'inférence de synthèse vocale.
- [extract_voice.py](extract_voice.py) : Script utilitaire pour extraire des échantillons audio.
- [Dockerfile](Dockerfile) : Configuration de l'image Docker ciblant une exécution GPU (PyTorch+CUDA).
- **voices/** : Dossier contenant les échantillons audio `.wav` de référence pour le clonage de voix.
