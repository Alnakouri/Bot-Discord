# Instructions pour les agents IA (Cursor, Gemini, Claude, Copilot, etc.)

> **LIRE EN PREMIER avant toute modification de code.**
> **Lire ARCHITECTURE.md pour le contexte complet du projet.**

---

## 🚨 INTERDICTIONS ABSOLUES

1. **NE JAMAIS supprimer, écraser ou modifier un fichier `.env`** — ils contiennent des clés API de production
2. **NE JAMAIS supprimer ou modifier un fichier `.master_key`** — clés de chiffrement Fernet
3. **NE JAMAIS créer d'import direct entre deux bots** (ex: `from Alfred.bot_alfred import ...` dans Sheogorath)
4. **NE JAMAIS factoriser le code "dupliqué" entre bots** — l'indépendance est VOULUE
5. **NE JAMAIS changer le mode journal SQLite** (WAL) dans `shared_database.py`
6. **NE JAMAIS commiter de fichiers `.env`, `.master_key`, ou `*.db`** dans Git

## 🏗️ Règles architecturales

- **Chaque bot est indépendant** : il peut tourner seul, sans les 5 autres, et sans `shared/`
- **`shared/` est optionnel** : tous les imports `shared.*` doivent avoir un `try/except ImportError`
- **Chaque bot a ses propres** : `.env`, `requirements.txt`, `discloud.config`
- **Le code identique entre bots est normal** — ne pas le fusionner dans un module commun
- Si tu modifies `shared/`, ça affecte les 6 bots — teste avec prudence

## 📝 Conventions de code

- Logger : utiliser `shared.bot_logger.setup_logger("nom_bot")` (avec fallback `logging.getLogger`)
- Tâches périodiques : utiliser `@tasks.loop()` de discord.py (pas `asyncio.create_task` avec boucle while)
- Pattern `load_secure_env` : toujours appeler avec `Path(__file__).parent` et utiliser `os.getenv()` après
- Variables `keyword_boost` et `duel_context` : toujours initialiser à `""` en début de `on_message`

## 🔑 Fichiers sensibles (ne pas toucher)

```
Alfred/.env
Sheogorath/.env
MaiqBot/.env
JohnnyBot/.env
SugarBot/.env
MalenaBot/.env
.master_key
MalenaBot/.master_key
data/bots_database.db
data/api_usage.db
```
