# PLAN — M'aiq muet : PermissionError dans `on_message` (durcissement)

## Symptôme observé (13:24, live Discord)
`maiq`, `m'aiq`, `@M'aiq` → **aucune réponse**. Les 5 autres bots répondent
normalement au même moment.

## Cause racine (confirmée dans `docker logs bot-maiq`)
```
File "/app/bot/bot_maiq.py", line 1218, in on_message
    save_data(data)
File "/app/bot/bot_maiq.py", line 64, in save_data
    with open(DATA_FILE, "w") as f:
PermissionError: [Errno 13] Permission denied: '/app/data/maiq_data.json'
```
Le conteneur tourne en `botuser` (uid 10001). Six fichiers du bind mount
`./data` étaient `root:root 644` → écriture impossible :
`maiq_data.json`, `maiq_facts.json`, `maiq_memory.json`,
`maiq_memory_archive.jsonl`, `alfred_facts.json`, `alfred_memory_archive.jsonl`.

Le `save_data()` du **système de fatigue** est appelé *avant* la génération de la
réponse (bot_maiq.py:1218). L'exception remonte, `discord.py` l'avale
(« Ignoring exception in on_message ») et **la réponse n'est jamais produite** :
le bot paraît mort alors qu'il est up et connecté.

## Correctif immédiat (DÉJÀ APPLIQUÉ — 2026-08-13, hors code)
`docker exec -u 0 bot-maiq chmod 666` sur les 6 fichiers ci-dessus.
Vérifié : `os.access(..., os.W_OK)` → True pour les 4 fichiers M'aiq.
Aucun redémarrage nécessaire. **Reste : test live user** (« maiq » dans Discord).

---

## Travail à faire (Antigravity)

### 1. `save_data` / `load_data` ne doivent JAMAIS tuer `on_message`
Une écriture d'état (compteur de fatigue, pinces) est cosmétique : son échec ne
doit pas empêcher le bot de parler. Aujourd'hui trois bots partagent le même
pattern nu :

- `MaiqBot/bot_maiq.py:57-65`
- `JohnnyBot/bot_johnny.py:49-57`
- `SugarBot/bot_sugar.py:48-61`

Dans les trois fichiers, envelopper :

```python
def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"⚠️ Lecture {DATA_FILE} impossible ({e}) — valeurs par défaut.")
    return {...}   # ← garder le dict par défaut existant de chaque bot

def save_data(data):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f)
    except OSError as e:
        logger.warning(f"⚠️ Sauvegarde {DATA_FILE} impossible ({e}) — état non persisté.")
```

Contraintes :
- garder le dict par défaut propre à chaque bot (M'aiq `{"calipers": 0, "fatigue": ...}`,
  Johnny `{"missions_completed": ...}`, Sugar `{"tales_told": 0}`) ;
- Sugar a une migration `legends_told` → `tales_told` dans `load_data` : la
  conserver **à l'intérieur** du `try` ;
- si `logger` n'est pas encore défini au point du fichier, utiliser `logging.getLogger(...)`
  ou déplacer les fonctions après l'init du logger — pas de `print`.

### 2. Filet infra : perms du bind mount au démarrage
`deploy/setup_oracle.sh:21` fait déjà `chown -R 10001:10001 data logs`, mais rien
ne le rejoue en local (Docker Desktop / Windows) ni après création d'un fichier
par un process hôte (pytest, dashboard, script `tools/`).

Ajouter un garde au démarrage, au choix — **préférence : (a)**, zéro impact image :

(a) dans `shared/` un helper `ensure_data_writable()` appelé au boot de chaque bot,
    qui teste `os.access(DATA_DIR, os.W_OK)` + chaque `<bot>_*.json` et **logge un
    WARNING explicite** listant les fichiers non inscriptibles (pas de chmod : le
    conteneur n'est pas root). Objectif : rendre la panne visible en 1 ligne de log
    au lieu d'un traceback noyé 200 lignes plus bas.
    ⚠️ Respecter la règle « bots indépendants » : import en `try/except ImportError`
    avec fallback no-op.

(b) alternative : `chmod 666` dans un entrypoint root qui `su` vers botuser —
    plus lourd, touche le Dockerfile des 6 bots. Ne faire que si (a) est jugé
    insuffisant.

### 3. Vérification
- `pytest` (ne doit rien casser ; 242 tests verts attendus).
- Sonde manuelle : `docker exec -u 0 bot-maiq chmod 444 /app/data/maiq_data.json`
  puis écrire « maiq » dans Discord → **le bot doit répondre quand même**, avec un
  WARNING « Sauvegarde impossible » dans les logs. Remettre `chmod 666` après.

### 4. Déploiement
`docker compose up -d --build maiq johnny sugar` (le code est monté en `:ro`
depuis l'hôte, mais rebuild pour rester cohérent avec les autres déploiements).

---

## Gotchas
- Horloge conteneur = **UTC**, soit **-2h** par rapport à l'affichage Discord :
  le crash « 11:24:04 » dans les logs = 13:24 à l'écran.
- `docker logs bot-maiq` est la bonne source ; `logs/maiq_*.log` côté hôte s'arrête
  au 11 juin (le logger fichier n'écrit plus, à regarder un jour — hors scope ici).
- Les lignes `[DEBUG RIDDLE] User: ...` sont des `print` bruts qui polluent les logs
  du conteneur ; candidat à un `logger.debug` (hors scope).
