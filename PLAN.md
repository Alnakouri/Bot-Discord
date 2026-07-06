# PLAN — Dashboard : coexistence SQLite avec les bots Docker (+ rapport réel)

## Contexte & bug (diagnostic déjà fait, prouvé)
Le **dashboard** tourne comme **process Windows** (`python dashboard/backend/app.py`, lancé par
`start_dashboard.bat`). Les **bots** tournent en **conteneurs Docker** et montent `./data` en
**bind-mount** (`./data:/app/data`). Depuis le plan de fiabilisation, le dashboard OUVRE les bases
SQLite **partagées** avec les bots :
- `data/bots_database.db` — écritures (journal d'audit) + lectures (error/conversation analyzers, report) ;
- `data/api_usage.db` — lectures (api_tracker) — écrit par les bots via `shared/api_manager.py`.

Sur un **bind-mount Windows (Docker Desktop)**, le verrou SQLite pris côté **Windows** bloque les
conteneurs **Linux** → **tous les bots** lèvent `sqlite3.OperationalError: unable to open database file`
(à l'init `shared/shared_database.py:45` → crash-loop ; ou en runtime sur `get_config`/`is_maintenance_mode`
→ **le bot ne répond plus** sans crasher). Symptômes vécus 2026-07-06 : **Sugar muet**, **Malena crash-loop**.

**Preuves du diagnostic** (pour comprendre, ne pas refaire) :
- Une DB **neuve** créée dans `/app/data` s'ouvre sans problème → le montage/verrous vont bien.
- Une **copie** de `bots_database.db` s'ouvre avec `PRAGMA integrity_check = ok` → **pas corrompue**, juste **verrouillée**.
- `Stop-Process` du process dashboard Windows → la DB se débloque **instantanément** (test `docker exec bot-alfred` = OK).
- `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` → le seul process bot n'existe pas ;
  le verrou venait bien de `python backend\app.py` (le dashboard).

Voir aussi le gotcha n°6 dans la note mémoire `gotchas-docker-bots`.

## Objectif
Le dashboard (Windows) et les bots (Docker) doivent partager les SQLite **sans se bloquer** :
1. Le dashboard **n'ÉCRIT plus** dans les DB partagées → son **journal d'audit** va dans une **DB propre**.
2. Toutes les **LECTURES** dashboard des DB partagées passent en **read-only** (`mode=ro`) : pas de
   création de journal, pas de verrou d'écriture, uniquement des verrous SHARED brefs qui ne bloquent
   pas les écritures des bots.
3. Seule exception d'écriture tolérée : « marquer une erreur résolue » (rare, clic utilisateur) — garder
   une connexion write **brève et bornée**.

## ⚠️ POINTS CRITIQUES (à lire avant de commencer)
1. **RO URI sur Windows avec espace dans le chemin** (le repo est sous `I:\IA\Bot Discord\`, avec un ESPACE) :
   construire l'URI avec `pathlib.Path(db_path).absolute().as_uri()` (qui percent-encode l'espace → `%20`)
   puis suffixer `"?mode=ro"`, et `sqlite3.connect(uri, uri=True, timeout=20)`.
   **NE JAMAIS** concaténer un chemin brut Windows (backslashes) dans une URI.
   Exemple attendu : `file:///I:/IA/Bot%20Discord/data/bots_database.db?mode=ro`.
2. **`mode=ro` exige que le fichier EXISTE** (il ne le crée pas). Les analyzers gardent déjà
   `if not os.path.exists(self.db_path): return ...` → OK, ne pas retirer ces gardes.
3. **Ne PAS toucher** à l'authentification, au bind réseau, au CORS (hors périmètre, audités).
4. **Gotcha dev local** : après toute modif d'un fichier `backend/`, **relancer `start_dashboard.bat`**
   (pas de hot-reload).
5. **Rester en vanilla** (pas de dépendance nouvelle). Tout se fait avec `sqlite3` + `pathlib` de la stdlib.

## Fichiers & changements

### 1. Journal d'audit sur une DB dédiée (supprime les écritures fréquentes sur `bots_database.db`)
**Fichier** : `dashboard/backend/app.py`
- Ajouter, près de la déclaration des chemins (l.~126-127) :
  ```python
  DASHBOARD_DB_PATH = DATA_DIR / "dashboard_audit.db"  # DB propre au dashboard, aucun bot ne l'ouvre
  ```
- Modifier l'instanciation (l.136) :
  ```python
  audit_analyzer = AuditAnalyzer(str(DASHBOARD_DB_PATH))
  ```
- `dashboard/backend/audit_analyzer.py` : **inchangé** (il crée sa table `audit_logs` dans le `db_path`
  reçu ; il pointera maintenant sur `dashboard_audit.db`).
- Conséquence acceptée : l'historique d'audit déjà écrit dans `bots_database.db` (table `audit_logs`)
  est **abandonné** (le journal repart de zéro dans la nouvelle DB). Pas de migration (hors périmètre).

### 2. Lectures read-only sur `bots_database.db`
**Fichiers** : `dashboard/backend/conversation_analyzer.py`, `dashboard/backend/error_analyzer.py`,
`dashboard/backend/app.py`
- **conversation_analyzer.py** `_get_connection` : ouvrir en RO (toutes ses requêtes sont des `SELECT`).
  ```python
  def _get_connection(self):
      if not os.path.exists(self.db_path):
          return None
      from pathlib import Path
      conn = sqlite3.connect(Path(self.db_path).absolute().as_uri() + "?mode=ro", uri=True, timeout=20)
      conn.row_factory = sqlite3.Row
      return conn
  ```
- **error_analyzer.py** `_get_connection` : ajouter un paramètre `write=False`.
  - RO par défaut (comme ci-dessus) ; utilisé par `get_errors`, `analyze`, `count_recent`.
  - `resolve()` appelle `self._get_connection(write=True)` → connexion **normale** (write) :
    `sqlite3.connect(self.db_path, timeout=20)`.
- **app.py ~l.281** (le `sqlite3.connect(error_analyzer.db_path)` qui fait juste un `SELECT bot_name`
  pour l'audit) : passer en RO (même patron URI). C'est une lecture, aucune raison d'y prendre un verrou write.

### 3. `api_usage.db` : dashboard en lecture seule
**Fichier** : `dashboard/backend/api_tracker.py`
- `api_usage.db` est **écrit par les bots** (`shared/api_manager.py`). Le dashboard ne doit être que **lecteur**.
- `api_tracker` ne fait actuellement que `CREATE TABLE IF NOT EXISTS` (×2, l.20 & l.31) + des lectures :
  - **Retirer les `CREATE TABLE IF NOT EXISTS`** du dashboard (les tables sont créées côté bots) OU les
    déplacer dans un try/except toléré — mais l'objectif est que la connexion dashboard soit **RO**.
  - Passer `sqlite3.connect(self.db_path, ...)` (l.13) en **RO** (même patron URI `mode=ro`), avec la garde
    `os.path.exists` (créer la garde si absente : si `api_usage.db` n'existe pas encore, retourner un
    résultat vide plutôt que crasher).
- Vérifier les endpoints `/api/api-usage*` d'`app.py` : ils doivent tous passer par `api_tracker` (RO),
  aucun `sqlite3.connect` write direct sur `api_usage.db`.

### 4. (Optionnel, DRY) petit helper partagé
- Factoriser le patron RO dans un `dashboard/backend/db_utils.py` :
  ```python
  import sqlite3, os
  from pathlib import Path
  def connect_ro(db_path, timeout=20):
      if not os.path.exists(db_path):
          return None
      conn = sqlite3.connect(Path(db_path).absolute().as_uri() + "?mode=ro", uri=True, timeout=timeout)
      conn.row_factory = sqlite3.Row
      return conn
  ```
  et l'importer dans les 3 analyzers. (Facultatif ; si plus simple d'inliner, accepté.)

## SECONDAIRE (découvert en route) — le « rapport réel » est encore un STUB
**Fichier** : `dashboard/backend/report_generator.py`
- Malgré le commit `a79d245` (« rapport markdown réel »), `ReportGenerator.generate()` renvoie TOUJOURS
  un **stub** : `"Ceci est un rapport généré automatiquement..."` (seul le front download/copie a été fait).
  Le § 3.3 du plan précédent n'a donc été exécuté qu'à moitié.
- L'implémenter réellement (comme prévu à l'origine) : composer le Markdown depuis les managers déjà
  câblés dans `app.py` — statut des 6 bots (`BotManager`), erreurs non résolues (`ErrorAnalyzer`), usage
  API par provider (`APITracker`), stats conversations (`ConversationAnalyzer`), clés mortes/cooldown ;
  conserver l'en-tête « Instruction pour IA » en fin. Injecter les managers via le constructeur
  (`ReportGenerator.__init__`) depuis `app.py`.
- **Cohérence avec ce plan** : `report_generator` doit lire via les managers **déjà en RO** (ci-dessus),
  ne PAS rouvrir `bots_database.db` en write.
- (Si tu préfères, ce point peut être traité dans un second temps — il est indépendant du fix de verrou.)

## CRITÈRES DE VÉRIFICATION (avant de conclure)
- [ ] `python -m py_compile` sur tous les `.py` modifiés de `dashboard/backend/`.
- [ ] **Les 6 bots Docker TOURNENT** ; lancer le dashboard (`start_dashboard.bat`) et naviguer TOUTES les
      vues (stats, graphiques, erreurs, journal d'audit, santé cascade LLM, rapport).
- [ ] Pendant que le dashboard tourne, test décisif :
      ```
      docker exec bot-alfred python3 -c "import sqlite3; c=sqlite3.connect('/app/data/bots_database.db', timeout=5); c.execute('CREATE TABLE IF NOT EXISTS _t(x)'); c.execute('DROP TABLE _t'); c.commit(); print('DB_OK')"
      ```
      → doit afficher **`DB_OK`** (avant le fix : `unable to open database file`).
- [ ] `docker logs` des 6 bots : **AUCUN** `unable to open database file` après démarrage du dashboard.
- [ ] Le journal d'audit s'écrit dans **`data/dashboard_audit.db`** (nouveau fichier), plus dans
      `bots_database.db`. « Marquer une erreur résolue » fonctionne toujours.
- [ ] grep de contrôle : aucun `sqlite3.connect(<...bots_database.db|api_usage.db...>)` en mode **écriture**
      dans `dashboard/backend/`, **sauf** `error_analyzer.resolve` (write assumé, rare).

## Ordre & commits suggérés (français, 1 commit par bloc)
1. `fix(dashboard): journal d'audit sur une base dédiée (dashboard_audit.db)` (§1)
2. `fix(dashboard): lectures des bases partagées en read-only (anti-verrou bind-mount Windows)` (§2 + §3)
3. `feat(dashboard): rapport système réel, fin du stub` (SECONDAIRE — peut être un lot séparé)

## Hors périmètre (ne PAS faire)
- Auth / bind réseau / CORS.
- Migration de l'historique d'audit existant.
- Renommage Discord (étape manuelle au Developer Portal : Application name + Bot username = « Sugar Bot »).
- Modifier le code des bots (`shared/`, `SugarBot/`, etc.) — ce plan est 100 % contenu dans `dashboard/`.
