# 📊 Optimisations & Historique des Changements

## Avril 2026 — Refactoring & Dockerisation

### Centralisation (Phase 1)
- **shared_database.py** : Centralisé dans `shared/` → une seule source de vérité.
- **secure_env.py** : Centralisé dans `shared/` → chiffrement unifié Fernet.
- **slash_commands.py** : Centralisé dans `shared/` → 7 commandes (/reputation, /leaderboard, /birthday, /quests, /stats, /ping, /help).
- **response_memory.py** : Nouveau module anti-répétition partagé.
- **bot_base.py** : Classe de base pour standardiser l'initialisation.

### Corrections (Phase 2)
- **Johnny/Zaji** : Suppression du double calcul `should_respond` dans `on_message`.
- **Alfred** : Suppression du double appel `load_secure_env()`.
- **Sheogorath** : Suppression de la double définition de `status_loop_sheo`.
- **Malena** : Migration de `discord.Client` vers `commands.Bot`.
- **Clés Gemini** : Unification `GEMINI_KEY_1` à `GEMINI_KEY_4` pour tous les bots.

### Modernisation (Phase 3)
- Modèle principal : `gemini-1.5-flash` → **`gemini-2.0-flash`**
- Fallback OpenRouter : `gemma-3-27b-it:free` → **`gemma-4-26b-a4b-it:free`**
- Ajout de `graceful_shutdown.py` — arrêt propre via SIGTERM/SIGINT (Docker).
- Ajout de `healthcheck.py` — monitoring minimal.

### Dockerisation (Phase 5)
- `Dockerfile` + `docker-compose.yml` pour orchestrer les 6 bots.
- Base de données SQLite unique dans `data/bots_database.db`.
- Volumes persistants pour données, logs et mémoires.

### Multimodal & API Intelligence (Phase 6 - Avril 16)
- **Vision & Audio** : Support complet des images et des messages vocaux Discord dans TOUS les bots.
- **shared/media_handler.py** : Nouveau moteur multimodal unifié (transcription audio + analyse vision).
- **shared/smart_router.py** : Détection des messages vocaux (.ogg) et routage prioritaire vers Gemini Flash.
- **Rotation Round-Robin** : Équilibrage de charge intelligent entre les clés API pour éviter la saturation.
- **TPM/RPM Tracking** : Suivi en temps réel des "Tokens Per Minute" pour chaque clé avec fenêtre glissante de 60s.
- **Persistance DB** : Les erreurs et quotas des clés sont synchronisés dans `data/api_usage.db`.
- **Dashboard Santé** : Nouvel onglet de monitoring des clés (TPM, RPM, Quotas restants).

---

## Janvier 2026 — Corrections Gemini

### Erreur 404 Gemini (Critique)
- **Cause** : Le SDK `google-genai` activait Vertex AI automatiquement si `GOOGLE_CLOUD_PROJECT` existait.
- **Fix** : Création de `shared/safe_client.py` qui nettoie les variables d'environnement avant l'instanciation du client.

### Erreur 429 (Rate Limiting)
- **Fix** : `shared/api_manager.py` avec rotation automatique des clés et cooldown de 60s par clé bloquée.

### Performance
- Limitation de l'historique de conversation à 15 messages max.
- Timeouts configurables pour les appels API (30s par défaut).
