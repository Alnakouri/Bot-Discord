# PLAN — Rebrancher `error_events` : la vue « Analyse Erreurs » cesse d'être vide

Rédaction : Claude, le **2026-09-10**. Exécution : **Antigravity**.
Décision utilisateur du 10/09 : **« on rebranche »** (l'autre option était de retirer la vue).

Le portage du dashboard v2 est clos (`5ab840b`, CI verte, parcours au clic validé). Ceci
est le dernier chantier qu'il avait exhumé.

---

# LE CONSTAT

`shared/shared_database.py:916` définit `log_error_event(...)`. **Aucun appelant n'existe
dans le dépôt.** Les 10 lignes de `error_events` datent du 8-9 juin 2026.

Conséquences visibles côté dashboard :
- la vue « Analyse Erreurs » est vide en permanence ;
- la tuile « Erreurs (24 h) » affiche `0` quoi qu'il arrive ;
- la moitié erreurs du bandeau d'alerte ne peut jamais se déclencher.

## Ce que la mesure dit — à lire avant de dimensionner quoi que ce soit

Compté sur les `logs/*_structured.jsonl` réels des 6 bots, le 10/09 :

- **8 lignes `ERROR`/`CRITICAL` sur 7 jours**, dont **0 sur les dernières 24 h**.
- Réparties sur 2 bots seulement : `johnny` (6), `sheogorath` (2).
- Et ce sont **4 motifs**, tous au **démarrage** :
  `[SLASH] Erreur: Command 'reputation' already registered.` et
  `[GAMES] Erreur d'initialisation des mini-jeux: The command j...`

**Il n'y a donc pas de risque de flot.** Ne pas construire d'anti-flood, de
dé-duplication, ni de fenêtre de regroupement : ce serait de la complexité pour un volume
d'environ **une erreur par jour**. La file bornée suffit (voir plus bas).

⚠️ **Mais il y a un risque de bandeau qui crie pour du nominal**
([[gotcha-alerte-qui-crie-pour-du-nominal]]). `error_analyzer.count_recent()` compte les
lignes **non résolues** et le bandeau s'allume dès `> 0` : au premier redémarrage après
déploiement, les 4 motifs ci-dessus produiront des lignes et le bandeau dira
« N erreurs sur 24 h ». C'est **correct** — ce sont de vraies erreurs, et le dashboard a
un bouton « résoudre ». Mais il faut le savoir avant de l'attribuer au nouveau code. Les
deux erreurs de démarrage sont par ailleurs de vrais défauts à corriger un jour : elles
sont **hors périmètre de ce plan**, à ne pas toucher ici.

---

# LA DÉCISION D'ARCHITECTURE, ET POURQUOI

## Le handler vit dans `shared/bot_logger.py`, pas dans un nouveau module

`bot_logger.py` est **déjà vendorisé** (`tools/vendor_core.py` ligne 11 et
`tools/sonde_core_drift.py` ligne 11), et **déjà importé par les 6 bots** — vérifié :

| Bot | Ancre |
|---|---|
| Alfred | `Alfred/bot_alfred.py:71-72` — `setup_logger("alfred")` |
| Johnny | `JohnnyBot/bot_johnny.py:43-44` — `setup_logger("johnny")` |
| M'aiq | `MaiqBot/bot_maiq.py:58-59` — `setup_logger("maiq")` |
| Malena | `MalenaBot/bot_malena.py:56` + `:102` — `setup_logger("malena", "logs")` |
| Sheogorath | `Sheogorath/bot_sheogorath.py:122-123` — `setup_logger("sheogorath")` |
| Sugar | `SugarBot/bot_sugar.py:40-41` — `setup_logger("sugar")` |

Les 6 identifiants correspondent exactement à ceux du dashboard (`botDisplayNames` dans
`app.js`), donc le filtre par bot de la vue « Analyse Erreurs » marchera sans traduction.

**Conséquence : aucun nouveau module, donc aucune liste de vendoring à toucher.** C'est
délibéré — [[gotcha-deux-listes-vendoring]] est la panne la plus répétée du dépôt, et
[[gotcha-un-bot-sur-six-manque-toujours]] la seconde. Ce plan ne les rend pas possibles.

## Le handler N'APPELLE PAS `shared_database.log_error_event`

Deux raisons, dans cet ordre :

1. **`shared_database.py` n'est pas vendorisé.** Un bot déployé seul, sans `shared/`, ne
   peut pas l'importer ([[bots-independants]],
   [[decision-independance-stricte-vendoring-core]]). Le handler doit tenir dans le module
   vendorisé, avec son propre `sqlite3`.
2. **`log_error_event` écrit en synchrone, dans le thread appelant.** Une erreur se
   journalise depuis `on_message`, donc **dans la boucle asyncio**. Le commentaire de
   `shared/api_tracking.py` est explicite et vaut ici mot pour mot :
   *« Surtout PAS une deuxième connexion SQLite depuis `on_message` : 6 conteneurs sur un
   bind mount Windows, c'est le montage exact du `disk I/O error` de la mémoire. »*

`log_error_event` **reste en place**, inchangé : c'est la référence de schéma et un
helper en-processus légitime. Il restera sans appelant — c'est assumé, pas un oubli.

## Le modèle à copier : `shared/api_tracking.py`

File `queue.Queue(maxsize=1000)` + **un** thread écrivain démon + une connexion SQLite
unique dans ce thread. Reprendre la structure de `api_tracking.py` **à l'identique** :
`_ECRIVAIN_HS`, les drapeaux `_JOURNAL_*` qui n'avertissent qu'une fois, `_ensure_thread()`
sous verrou, `_empiler()` qui absorbe `queue.Full`.

⚠️ **`_queue.task_done()` doit être dans un `finally`.** Hors `finally`, un `join()`
pend à jamais — c'est le bug de [[plan-suivi-appels-api]], déjà payé une fois. Regarder
`api_tracking._writer_loop` : le `try/finally` interne est là pour ça.

---

# LE TRAVAIL, ÉTAPE PAR ÉTAPE

## Étape 1 — `ErrorEventHandler` dans `shared/bot_logger.py`

Ajouter, **après** la classe `JSONLHandler` (qui finit ligne 35) et **avant**
`def setup_logger` (ligne 37). Les imports à ajouter en tête de fichier (lignes 3-7) :
`queue`, `sqlite3`, `threading`, `traceback`, `from pathlib import Path`.

### Le chemin de base

Exactement la même résolution que `api_tracking._get_connection`, **mais sur l'autre
fichier** :

```python
data_dir = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
db_path = os.path.join(data_dir, "bots_database.db")
```

⚠️ `api_usage.db` est une **autre** base. `error_events` vit dans `bots_database.db` —
c'est celle que `dashboard/backend/app.py:143` passe à `ErrorAnalyzer`. Se tromper de
fichier donne un code qui marche, des tests verts, et une vue toujours vide.

⚠️ **Ne pas poser de `PRAGMA journal_mode`.** `shared_database.get_connection()` gère
déjà le journal de cette base, et [[gotcha-sqlite-wal-bind-mount]] dit qu'un
`journal_mode` peut rendre un autre mode sans lever. Se contenter de
`sqlite3.connect(db_path, timeout=20)` et de `PRAGMA synchronous=NORMAL` en `try/except`.

### La table

`CREATE TABLE IF NOT EXISTS error_events (...)` **strictement identique** à
`shared/shared_database.py:172-183` — recopier les 10 colonnes telles quelles, y compris
`resolved INTEGER DEFAULT 0` et `report_generated INTEGER DEFAULT 0`. Elle sert au cas où
un bot démarre avant que le dashboard n'ait créé la base. Un verrou de test compare les
deux (étape 4).

### Les champs écrits — la contrainte la plus importante du plan

| Colonne | Valeur | Piège |
|---|---|---|
| `timestamp` | `datetime.now().isoformat()` | — |
| `bot_name` | **le `bot_name` passé à `__init__`** | ⚠️ **PAS `record.name`.** `JSONLHandler` écrit `record.name`, qui pour les loggers partagés vaut `"smart_router"`, `"llm_cascade"`… — pas le bot. Le handler doit prendre `bot_name` en argument, comme `JSONLHandler` le fait pour son chemin. |
| `error_type` | `record.exc_info[0].__name__` si `record.exc_info`, sinon `record.module` | — |
| `error_message` | `record.getMessage()` | tronquer à 2000 caractères |
| `error_traceback` | `"".join(traceback.format_exception(*record.exc_info))` si présent, sinon `None` | **tronquer à 8000 caractères** — une trace peut être énorme |
| `context_json` | `json.dumps({"module": record.module, "funcName": record.funcName, "lineno": record.lineno})` | ⚠️ **exactement ces trois clés, ces trois noms.** |
| `severity` | `record.levelname` | vaudra `ERROR` ou `CRITICAL` |

⚠️ **`context_json` n'est pas libre.** Le bloc « Origine » du détail d'erreur, récrit à la
relecture du Lot 2, lit `module`, `funcName` et `lineno` — il a été construit sur ce que
les 10 lignes de juin contenaient réellement. Une quatrième clé, ou un nom différent, et
le détail d'erreur redevient un bloc vide : c'est **exactement** le défaut n° 3 du Lot 2,
qui devinait ses clés. Ne pas enrichir ce dictionnaire « tant qu'on y est ».

### `emit()` ne lève jamais, et ne se rappelle jamais lui-même

- Tout le corps dans un `try/except Exception: pass`, comme `JSONLHandler.emit` — la
  raison est écrite dans son commentaire : *« Ne jamais crasher le bot pour un log »*.
- **Garde anti-récursion** : `if record.name == __name__ or record.name == "bot_logger":
  return` au tout début. Le thread écrivain journalise ses propres pannes ; sans cette
  garde, une panne d'écriture produit une erreur, qui produit une écriture, qui échoue.
- Le handler est posé à `setLevel(logging.ERROR)` : `WARNING` et `INFO` ne doivent
  produire **aucune** ligne.

## Étape 2 — le câblage dans `setup_logger`

Point d'insertion : **entre la ligne 107 (`logger.addHandler(jsonl_handler)`) et la
ligne 109 (`for shared_name in (...)`)**, à l'intérieur du bloc `if not console_only:`.

```python
        # Handler « evenements d'erreur » pour la vue Analyse Erreurs du dashboard.
        # Pose AVANT la boucle ci-dessous : c'est elle qui recopie logger.handlers
        # sur les loggers des modules partages.
        erreurs_handler = ErrorEventHandler(bot_name)
        erreurs_handler.setLevel(logging.ERROR)
        logger.addHandler(erreurs_handler)
```

⚠️ **L'ordre n'est pas cosmétique.** La boucle des lignes 109-115 recopie
`logger.handlers` — l'état de la liste **à cet instant** — sur les loggers partagés. Posé
après la boucle, le handler ne verrait aucune erreur de `smart_router`, `llm_cascade`,
`media_handler`, `safe_client`, `discord_status`, `discord_profile`. Un test verrouille
cet ordre (étape 4, mutation n° 6).

⚠️ **Rester dans `if not console_only:`.** C'est la garde qui empêche `pytest` d'écrire
dans la base des bots live ([[gotcha-pytest-pollue-data]]) : `console_only` est vrai dès
que `PYTEST_CURRENT_TEST` ou `BOTS_LOG_CONSOLE_ONLY` est posé. Ne pas la contourner.

### Élargir la liste des loggers partagés

Ligne 109-110, la liste actuelle est :

```python
        for shared_name in ("smart_router", "llm_cascade", "media_handler",
                            "safe_client", "discord_status", "discord_profile"):
```

Y ajouter les autres modules du noyau vendorisé qui journalisent : **`api_manager`,
`api_tracking`, `response_memory`, `transcript`, `anti_tic`, `repartee_lessons`,
`boucles`**. Sans ça, leurs erreurs ne sont visibles que dans `docker logs` et
n'arriveront jamais dans la vue.

**Ne PAS poser le handler sur le logger racine.** Ce serait plus complet, mais ça
ramasserait aussi le bruit de `discord.py` (reconnexions de gateway, etc.) et ferait
exactement crier le bandeau pour du nominal. On reste sur le code du dépôt. Si la vue se
révèle utile et trop pauvre, on élargira **après mesure**, pas avant.

## Étape 3 — la remise à zéro pour les tests

Ajouter une `reinitialiser_pour_tests()` calquée sur celle d'`api_tracking.py` (fin de
fichier) : vider la file **avant** de poser la pilule empoisonnée — sur une file pleine,
un `put_nowait` lèverait `queue.Full` et l'écrivain ne s'arrêterait jamais — puis
`join(timeout=5.0)`, puis remettre tous les drapeaux à `False` et le thread à `None`.

Sans elle, le thread écrivain fuit d'un test à l'autre et la suite devient capricieuse.

**Limite assumée, à ne pas corriger ici** : `shared/graceful_shutdown.py` ne vide aucune
file — `api_tracking` ne le fait pas non plus. Le thread est un démon : au pire, la
dernière erreur en file est perdue à l'arrêt. Cohérent avec l'existant.

## Étape 4 — le verrou : `tests/test_error_events_handler.py`

Un fichier neuf. **Chaque test doit crier si on casse ce qu'il protège** : appliquer la
mutation, vérifier le rouge, remettre. Les 8 mutations à rejouer :

1. **Une ligne écrite par erreur.** Un `logger.error("boum")` produit exactement 1 ligne,
   `severity='ERROR'`. *Mutation : ne rien écrire → rouge.*
2. **`bot_name` est celui du bot, pas celui du logger.** Émettre depuis un logger nommé
   `"smart_router"` et vérifier que `bot_name` vaut le bot. *Mutation : écrire
   `record.name` → rouge.* **C'est le piège de `JSONLHandler` : ce test est le plus
   important du fichier.**
3. **`context_json` vaut exactement `{module, funcName, lineno}`.** Comparer l'ensemble
   des clés, pas seulement leur présence. *Mutation : ajouter une 4e clé → rouge ;
   renommer `funcName` en `func_name` → rouge.*
4. **Exception → type et trace.** `logger.error("x", exc_info=True)` dans un `except
   ValueError` : `error_type == "ValueError"`, `error_traceback` non nul et ≤ 8000
   caractères. *Mutation : ignorer `exc_info` → rouge.*
5. **Rien en dessous de `ERROR`.** `logger.warning(...)` et `logger.info(...)`
   n'écrivent aucune ligne. *Mutation : `setLevel(logging.WARNING)` → rouge.*
6. **L'ordre de pose.** Après `setup_logger`, le logger `"smart_router"` porte bien une
   instance d'`ErrorEventHandler`. *Mutation : déplacer `logger.addHandler(erreurs_handler)`
   après la boucle des lignes 109-115 → rouge.*
7. **`emit()` ne lève jamais.** Pointer `DATA_DIR` sur un chemin non écrissible (ou
   patcher `sqlite3.connect` pour lever) et vérifier que `logger.error(...)` retourne sans
   exception et sans boucler. *Mutation : retirer le `try/except` d'`emit` → rouge.*
8. **Les deux schémas sont égaux.** Extraire les colonnes de `CREATE TABLE error_events`
   dans `shared/bot_logger.py` et dans `shared/shared_database.py`, et comparer les listes
   `(nom, type)`. *Mutation : retirer `report_generated` d'un des deux → rouge.* C'est le
   verrou anti-dérive, dans l'esprit de [[gotcha-deux-listes-vendoring]].

⚠️ **Le test doit poser `DATA_DIR` sur un `tmp_path`** et construire `ErrorEventHandler`
directement — sous `pytest`, `console_only` est vrai, donc `setup_logger` ne l'attache
pas. Le test 6 est l'exception : il doit forcer `BOTS_LOG_CONSOLE_ONLY=""` **et**
`DATA_DIR=tmp_path` pour faire jouer la branche complète, puis appeler
`reinitialiser_pour_tests()`. **Ne jamais laisser un test écrire dans `data/` du dépôt.**

⚠️ Après chaque test qui a fait démarrer l'écrivain : `reinitialiser_pour_tests()` en
`finally` ou en fixture. Sinon le thread survit et le test suivant lit ses écritures.

## Étape 5 — vendoriser

```
python tools/vendor_core.py
python tools/sonde_core_drift.py
```

`bot_logger.py` est déjà dans les deux listes : **rien à ajouter**, mais les 6 copies
`<Bot>/core/bot_logger.py` doivent être régénérées et commitées. La CI a un job
« Le vendoring est bien a jour » qui échoue sinon.

---

# RECETTE

Dans cet ordre, et le premier d'abord :

1. **`pyflakes`** sur `shared/`, `tests/`, `tools/` — **avant** `pytest`
   ([[gotcha-suppression-par-motif-textuel]]).
2. **`pytest` seul**, jamais deux en parallèle (port 8599 et `data/` partagés
   — [[gotcha-pytest-pollue-data]]). Référence actuelle : **900 tests, 0 échec**.
3. **Vérifier qu'aucune ligne n'est apparue dans `data/bots_database.db`** pendant la
   suite : `SELECT COUNT(*) FROM error_events` doit valoir **10** avant comme après.
   C'est la preuve directe que la garde `console_only` tient.
4. **Les 8 mutations rejouées**, une par une, chacune vérifiée rouge.
5. `python tools/sonde_core_drift.py` : aucune dérive.

## Ce qui ne peut se constater qu'en live, après déploiement

- **Provoquer une vraie erreur** dans un conteneur et voir la ligne arriver. Le plus
  simple sans rien casser : redémarrer un bot — les 4 motifs de démarrage mesurés plus
  haut se déclencheront d'eux-mêmes.
- **Ouvrir la vue « Analyse Erreurs »** : la ligne s'affiche, le filtre par bot marche, le
  bloc « Origine » du détail affiche `module.fonction:ligne` (c'est le test de la
  contrainte `context_json`), et le bouton « résoudre » la fait sortir du compteur.
- **La tuile « Erreurs (24 h) »** et le bandeau d'alerte cessent d'être morts.
- ⚠️ **Vérifier `docker logs` juste après** : aucune boucle, aucun `disk I/O error`,
  aucun avertissement `[ERROR EVENTS]` répété. Borner avec `--since`
  ([[gotcha-docker-logs-sans-since]]).

---

# LES RÈGLES

1. **Ne pas toucher au dashboard** — ni `backend/`, ni `frontend/`. Tout ce qu'il faut y
   est déjà : les routes `/api/errors*`, la vue, le détail, le bouton « résoudre ». Ce
   chantier ne fait que **remplir la table**.
2. **Ne pas toucher à `shared_database.py`.** `log_error_event` reste, sans appelant.
3. **Ne pas corriger les 2 erreurs de démarrage** (`reputation already registered`,
   init des mini-jeux) — vrai sujet, autre chantier.
4. **Éditer les fichiers directement.** Pas de script Python jetable : c'est le mécanisme
   qui a produit les trois ruptures de syntaxe du Lot 2 du dashboard
   ([[gotcha-script-jetable-dit-success]]).
5. **Ne pas commiter, ne pas pousser, ne pas créer de branche.** La relecture commite.
6. **Rendre compte de ce qui n'a pas été fait**, nommément.
