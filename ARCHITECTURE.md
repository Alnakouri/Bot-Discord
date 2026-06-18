# 🏗️ ARCHITECTURE — Écosystème Discord Bots

> **Ce document est la constitution du projet. Toute modification DOIT respecter ces règles.**

---

## ⚠️ RÈGLES ABSOLUES (À LIRE AVANT TOUTE MODIFICATION)

### 🔴 RÈGLE #1 — Indépendance des Bots

**Chaque bot est un processus autonome et déployable indépendamment.**

- Chaque bot a son propre dossier (`Alfred/`, `Sheogorath/`, `MaiqBot/`, `JohnnyBot/`, `OnizukaBot/`, `MalenaBot/`)
- Chaque bot a ses propres fichiers : `.env`, `requirements.txt`, `discloud.config`, `bot_*.py`
- Chaque bot PEUT fonctionner SEUL sans les autres bots
- Chaque bot PEUT fonctionner SANS le dossier `shared/` (mode dégradé)
- **NE JAMAIS créer de dépendance directe entre deux bots**
- **NE JAMAIS importer du code d'un bot dans un autre bot**
- Le code "dupliqué" entre bots (initialisation clients IA, key manager, etc.) est **VOLONTAIRE** — ne pas le factoriser

### 🔴 RÈGLE #2 — Protection des Clés API

**Les fichiers `.env` contiennent des clés API EN PRODUCTION. Ne JAMAIS les supprimer, écraser ou modifier sans autorisation explicite.**

- **NE JAMAIS supprimer un fichier `.env`**
- **NE JAMAIS écraser le contenu d'un fichier `.env`**
- **NE JAMAIS commiter les `.env` dans Git** (ils sont dans `.gitignore`)
- **NE JAMAIS afficher/logger les valeurs des clés API**
- Si tu dois ajouter une variable d'environnement, **AJOUTE-LA à la fin** du `.env` existant
- Les `.master_key` (chiffrement Fernet) sont aussi des secrets critiques

### 🔴 RÈGLE #3 — Le dossier `shared/` est une bibliothèque OPTIONNELLE

- `shared/` contient des modules utilitaires utilisés par tous les bots
- Tous les imports de `shared.*` DOIVENT être protégés par `try/except ImportError`
- Si `shared/` est absent, le bot DOIT démarrer en mode dégradé (fonctionnalités réduites)
- Les modifications dans `shared/` affectent TOUS les bots — tester avec prudence

---

## 📁 Structure du Projet

```
Bot Discord/
├── Alfred/                  # Bot Alfred Pennyworth (Majordome cynique)
│   ├── bot_alfred.py        # Point d'entrée
│   ├── .env                 # 🔒 Secrets (NE PAS TOUCHER)
│   ├── requirements.txt     # Dépendances propres
│   └── discloud.config      # Config Discloud (déploiement solo)
│
├── Sheogorath/              # Bot Sheogorath (Prince de la Folie)
│   ├── bot_sheogorath.py
│   ├── sheo_voice.py        # 🎤 Système Vocal (Chatterbox Turbo)
│   ├── sheo_data.py         # Personnalité, répliques, données
│   ├── sheo_memory.py       # Système de mémoire
│   ├── sheo_punishments.py  # Système de punitions (Wabbajack)
│   ├── sheo_llm.py          # Post-processing LLM
│   ├── sheo_mentions.py     # Conversion mentions
│   ├── sheo_faveur.py       # Système de Faveur du Prince
│   ├── sheo_imposter.py     # Usurpation d'identité (Webhook)
│   ├── minigames.py         # Mini-jeux
│   └── backup_manager.py    # Backup automatique
│
├── chatterbox-server/       # 🔊 Serveur TTS (Voice Cloning)
│   ├── server.py            # API FastAPI pour TTS
│   ├── Dockerfile           # Image GPU (CUDA)
│   └── voices/              # Échantillons de voix (.wav)
│
├── MaiqBot/                 # Bot M'aiq le Menteur (Khajiit sage)
│   ├── bot_maiq.py
│   └── minigames.py
│
├── JohnnyBot/               # Bot Johnny Silverbot (Rockerboy Cyberpunk)
│   ├── bot_johnny.py
│   └── johnny_data.py       # Personnalité et données
│
├── OnizukaBot/              # Bot Eikichi Onizuka (Great Teacher Onizuka)
│   ├── bot_onizuka.py
│   └── onizuka_data.py
│
├── MalenaBot/               # Bot Malena (La Gitana Marseillaise)
│   ├── bot_malena.py
│   ├── malena_data.py       # Personnalité et expressions
│   └── malena_memory.py     # Système de mémoire
│
├── shared/                  # 📚 Bibliothèque partagée OPTIONNELLE
│   ├── api_manager.py       # MultiAPIKeyManager (round-robin, cooldowns, TPM)
│   ├── smart_router.py      # Classification des requêtes (TEXT/IMAGE/AUDIO/REASONING)
│   ├── media_handler.py     # Vision (Gemini + Ollama Moondream) + Audio
│   ├── shared_database.py   # SQLite centralisé (WAL mode)
│   ├── slash_commands.py    # Commandes slash Discord unifiées
│   ├── server_events.py     # Événements serveur (join/leave/birthday)
│   ├── bot_duel_tracker.py  # Anti-boucle duels inter-bots (JSON)
│   ├── secure_env.py        # Chargement .env chiffré (Fernet)
│   ├── safe_client.py       # Fix Gemini "Invalid project name"
│   ├── bot_logger.py        # Logger structuré (JSONL + Console)
│   ├── response_memory.py   # Anti-répétition (RAM)
│   ├── graceful_shutdown.py # Arrêt propre (SIGTERM/SIGINT)
│   ├── healthcheck.py       # Health check API
│   └── crypto_utils.py      # Chiffrement/déchiffrement Fernet
│
├── dashboard/               # 📊 Dashboard de monitoring
│   ├── backend/             # FastAPI (app.py + 6 modules)
│   └── frontend/            # Vanilla JS + CSS + Chart.js
│
├── data/                    # 📦 Données persistées (volumes Docker)
│   ├── bots_database.db     # SQLite partagé (WAL)
│   └── api_usage.db         # Tracking usage API
│
├── migrations/              # Scripts de migration DB
├── docker-compose.yml       # Orchestration 6 bots + Ollama
├── Dockerfile               # Image Python 3.11 + ffmpeg
├── requirements.txt         # Dépendances globales (Docker)
└── .gitignore               # Exclut .env, .master_key, *.db
```

---

## 🔧 Stack Technique

| Composant | Technologie | Version |
|---|---|---|
| Runtime | Python | 3.11 (Docker) |
| Framework Discord | discord.py | >=2.7.1 |
| IA Principale | Google Gemini | gemini-2.0-flash / gemini-2.5-pro |
| IA Fallback #1 | Mistral | mistral-large-latest |
| IA Fallback #2 | Groq | llama-3.3-70b-versatile |
| IA Fallback #3 | xAI Grok | grok-3-mini |
| IA Fallback #4 | OpenRouter | meta-llama/llama-3.3-70b-instruct |
| Vision locale | Ollama Moondream | moondream (conteneur Docker) |
| Base de données | SQLite | WAL mode, accès concurrent |
| Dashboard | FastAPI + Vanilla JS | Port 8501 (Orchestration Docker native) |
| Synthèse Vocale (V2)| Chatterbox (Turbo) | Zero-Shot Voice Cloning (GPU CUDA) |
| Conteneurisation | Docker Compose | 6 bots + 1 Ollama + 1 Chatterbox |

---

## 🔄 Pattern d'Initialisation Standard (chaque bot)

Chaque bot suit ce schéma — **ne pas le modifier** :

```python
# 1. INJECTION SHARED PATH
import sys, os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# 2. CHARGEMENT SÉCURISÉ DES VARIABLES D'ENVIRONNEMENT
from pathlib import Path
try:
    from shared.secure_env import load_secure_env
    load_secure_env(Path(__file__).parent)
except ImportError:
    from dotenv import load_dotenv
    load_dotenv()

# 3. IMPORT SAFE GEMINI CLIENT
from shared.safe_client import get_client as get_safe_genai_client

# 4. IMPORTS OPTIONNELS AVEC FALLBACK
try:
    from shared.shared_database import (...)
    from shared.slash_commands import setup_slash_commands, sync_slash_commands
    DATABASE_AVAILABLE = True
except ImportError as e:
    DATABASE_AVAILABLE = False

# 5. INITIALISATION KEY MANAGER (propre à chaque bot)
from shared.api_manager import MultiAPIKeyManager
key_manager = MultiAPIKeyManager()
key_manager.register_api("gemini", GEMINI_API_KEYS)
# ... etc

# 6. INITIALISATION CLIENTS IA (propre à chaque bot)
groq_client = None
try: groq_client = Groq(api_key=GROQ_API_KEY)
except: pass
# ... etc
```

---

## 🤖 Cascade Économique IA (Smart Router)

Les requêtes sont classifiées puis routées pour optimiser les coûts :

```
                    ┌─────────────────────┐
                    │  Message Utilisateur │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   classify_request   │
                    │   (smart_router.py)  │
                    └──────────┬──────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
    ┌──────▼──────┐    ┌──────▼──────┐    ┌───────▼───────┐
    │    TEXT      │    │   IMAGE     │    │  REASONING    │
    │  (simple)   │    │   AUDIO     │    │  (complexe)   │
    └──────┬──────┘    └──────┬──────┘    └───────┬───────┘
           │                  │                    │
     Mistral/Groq       Gemini Flash         Gemini Pro
     → OpenRouter       → Ollama local       (seul choix)
     → Gemini Flash      (Moondream)
```

---

## 📝 Notes pour les IA et développeurs

1. **Les fichiers bots sont volontairement grands** (800-1900 lignes). Sheogorath est le plus modularisé (9 fichiers auxiliaires). Les autres sont monolithiques par choix — ne pas refactorer sans accord.

2. **Les IDs Discord des bots sont hardcodés** dans les fichiers `bot_*.py` pour la détection inter-bots. Si un token est changé, mettre à jour les IDs dans TOUS les bots.

3. **La base SQLite est en mode WAL** pour supporter 6 processus concurrents. Ne pas changer le mode journal.

4. **Le duel tracker utilise un JSON partagé** (`duel_state.json`). C'est un point de fragilité connu (race conditions en Docker).

5. **Sheogorath bénéficie d'une voix haute fidélité** : Performance de Philippe Bozo (VF TESO) clonée via Chatterbox TTS. Le moteur vocal tourne sur GPU (CUDA) via un conteneur dédié (`chatterbox-tts`).
