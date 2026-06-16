# 🤖 Écosystème de Bots Discord — TES / Batman

Écosystème de **6 bots Discord** à personnalités distinctes, partageant une architecture centralisée et déployés via **Docker**.

## 🎭 Les Bots

| Bot | Personnalité | Spécialités |
|-----|-------------|-------------|
| **Sheogorath** | Prince de la Folie (TES) | Chaos, punitions, Wabbajack, **Acting Philippe Bozo (VF)** |
| **M'aiq le Menteur** | Khajiit menteur (TES) | Énigmes, rumeurs, mensonges |
| **Alfred Pennyworth** | Majordome (Batman) | Vocal TTS/STT, cynisme, service |
| **Johnny Silverbot** | Rockerboy (Cyberpunk 2077) | Anti-corpo, cynisme, provocation |
| **Za'ji** | Capitaine corsaire (TES) | Aventures, explosions, cuisine |
| **Malena** | Gitana marseillaise | Tarot, prédictions, sagesse gitane |

## 🏗️ Architecture

```
Bot Discord/
├── docker-compose.yml          # Orchestrateur des 6 bots
├── Dockerfile                  # Image commune Python 3.11
├── requirements.txt            # Dépendances partagées
├── .env.example                # Template des variables d'environnement
├── chatterbox-server/          # 🔊 TTS Engine (Voice Cloning)
│
├── shared/                     # Modules centralisés (DRY)
│   ├── api_manager.py          # Rotation clés Gemini/Groq
│   ├── bot_duel_tracker.py     # Duels inter-bots
│   ├── graceful_shutdown.py    # Arrêt propre (SIGTERM Docker)
│   ├── healthcheck.py          # Healthcheck centralisé
│   ├── response_memory.py      # Anti-répétition partagée
│   ├── safe_client.py          # Fix Vertex AI / Gemini SDK
│   ├── secure_env.py           # Chiffrement .env (Fernet)
│   ├── server_events.py        # Bienvenue / départ / anniversaires
│   ├── shared_database.py      # DB SQLite unique partagée
│   └── slash_commands.py       # Commandes slash (/reputation, /help)
│
├── data/                       # Volume persistant Docker
│   ├── bots_database.db        # Base de données unique
│   ├── logs/
│   └── memories/
│
├── Alfred/                     # Code spécifique au bot (avec sa clé .master_key locale)
├── MaiqBot/                    # Code spécifique au bot (avec sa clé .master_key locale)
├── MalenaBot/                  # Code spécifique au bot (avec sa clé .master_key locale)
├── JohnnyBot/                  # Code spécifique au bot (avec sa clé .master_key locale)
├── Sheogorath/                 # Code spécifique au bot (avec sa clé .master_key locale)
└── ZajiBot/                    # Code spécifique au bot (avec sa clé .master_key locale)
```

## 🚀 Démarrage

### Prérequis
- Docker + Docker Compose
- Fichiers `.env.encrypted` configurés dans chaque dossier bot
- Fichier `.master_key` propre présent dans chaque dossier bot

### Lancer les bots
```bash
docker compose up -d          # Démarrage en arrière-plan
docker compose logs -f        # Suivre les logs
docker compose down           # Arrêter proprement
```

### Sans Docker (développement local)
```bash
pip install -r requirements.txt
python Alfred/bot_alfred.py   # Lancer un bot individuellement
```

## 🧠 Stack IA

| Rôle | Modèle | Plateforme |
|------|--------|-----------|
| 🥇 Principal | `gemini-1.5-pro / flash` | Google AI (Requis pour Tools) |
| 🥈 Fallback rapide | `llama-3.3-70b-versatile` | Groq (gratuit) |
| 🥉 Fallback gratuit | `google/gemma-4-26b-a4b-it:free` | OpenRouter |
| 🏅 Fallback FR | `mistral-large-latest` | Mistral |
| 🎙️ Vocal (Sheo)| `Chatterbox-Turbo` | Local (Philippe Bozo Performance) |

## 🧠 Intelligence Agentique (Function Calling)

Les bots (`Sheogorath`, `M'aiq`, `Alfred`) ne sont plus de simples générateurs de texte, mais des **Agents Autonomes** capables de manipuler le serveur via des outils (`Tools`) :
- **Prise de décision** : L'IA décide d'elle-même quand punir, récompenser ou lancer un événement.
- **Boucle de rétroaction** : Les bots exécutent l'action, puis commentent le résultat de manière roleplay.
- **Persistance** : Les effets (comme le Wabbajack) survivent aux redémarrages des bots via `sheo_punishments.json`.

## ⚠️ Notes pour les Développeurs

Pour maintenir la stabilité du système, respectez les règles suivantes :

1. **Payload Gemini** : Ne jamais envoyer de messages consécutifs avec le même rôle (ex: deux blocs `user`). Fusionnez-les toujours dans un seul objet `Content` avec plusieurs `Part`.
2. **Gestion des Clés** : Utilisez exclusivement le `key_manager` (`MultiAPIKeyManager`) pour les appels API afin de bénéficier de la rotation et du cooldown automatique.
3. **Tools** : Toute nouvelle fonctionnalité "action" (ex: bannissement, quête, loot) doit être implémentée sous forme de `Tool` pour Gemini 1.5 plutôt que par des déclencheurs par mots-clés (Regex).
4. **Base de Données** : La DB est partagée. Verrouillez vos transactions s'il y a des écritures concurrentes lourdes.

## 🔒 Sécurité

Les fichiers `.env` sont chiffrés via **Fernet** (`cryptography`).

```bash
python crypto_utils.py encrypt   # Chiffre les .env → .env.encrypted
python crypto_utils.py decrypt   # Déchiffre pour édition
```

> **Important** : Ne jamais committer `.master_key` ni les `.env` en clair.

## ⚡ Commandes Slash

Tous les bots partagent les mêmes commandes :

| Commande | Description |
|----------|-------------|
| `/reputation [user]` | Affiche les points et le rang d'un utilisateur |
| `/leaderboard [top]` | Classement de réputation du serveur |
| `/birthday <jour> <mois>` | Enregistre votre date d'anniversaire |
| `/quests` | Affiche vos quêtes quotidiennes |
| `/stats` | Statistiques des duels inter-bots (30 jours) |
| `/ping` | Vérifie la latence du bot |
| `/help` | Liste des commandes disponibles |

## 📊 Base de Données

Une base SQLite unique (`data/bots_database.db`) partagée par tous les bots :
- `users` — Utilisateurs et interactions
- `reputation` — Points, rangs, streaks d'énigmes
- `birthdays` — Anniversaires enregistrés
- `riddles` — Énigmes actives (M'aiq / Sheogorath)
- `riddle_history` — Anti-doublon d'énigmes
- `interactions` — Historique des interactions utilisateurs
- `quests` — Quêtes quotidiennes
- `bot_interactions` — Stats des duels inter-bots
- `logs` — Logs centralisés
- `config` — Configuration (mode maintenance, etc.)
