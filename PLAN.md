# PLAN — SUITE 12 : les bases ne sont plus sauvegardées depuis le 13/09

Rédaction : Claude, le **2026-09-28**. Exécution : **Antigravity**, sauf les étapes marquées
**[Ahmed]**. Plan précédent (SUITE 11, livré `49fc3de`) lisible dans git (`4c62c97:PLAN.md`).

⚠️ **AUCUN REDÉMARRAGE des bots** dans ce plan. On AJOUTE un service ; on ne relance que
lui. Consigne d'Ahmed du 27/09 au soir.

**Destination : `D:\Sauvegardes\BotDiscord`** (décision d'Ahmed du 28/09). Le projet vit sur
`I:` (Crucial BX500, disque 1) ; `D:` est un **autre disque physique** (Seagate 2 To, disque 0,
887 Go libres). Une panne du disque du projet n'emporte donc plus ses sauvegardes. Vérifié
le 28/09 : Docker Desktop monte `D:/` dans un conteneur de l'image des bots.

---

## LE CONSTAT (vérifié par Claude le 28/09)

La seule sauvegarde automatique du dépôt est `daily_backup_check` dans
`Sheogorath/bot_sheogorath.py` (l.1245–1255, démarrée l.849–850), qui appelle
`Sheogorath/backup_manager.py`. **Elle ne produit rien, pour trois raisons
indépendantes** :

1. **Elle ne se déclenche presque jamais** : `@tasks.loop(hours=24)` puis
   `if datetime.now().hour == 3`. La boucle ne regarde l'heure qu'une fois par 24 h, à
   l'heure du démarrage du bot : elle ne sauvegarde que si Sheogorath a démarré entre 3 h
   et 4 h (UTC dans le conteneur).
2. **Même déclenchée, elle échouerait** : `BACKUP_DIR = Path(__file__).parent / "backups"`,
   soit `/app/bot/backups`, dans un dossier monté **en lecture seule**
   (`./Sheogorath:/app/bot:ro`, `docker-compose.yml`). Le dossier n'existe pas
   (`docker exec bot-sheogorath ls /app/bot/backups` : absent).
3. **Elle viserait les mauvais fichiers** : `FILES_TO_BACKUP` liste `bots_database.db`,
   `Sheogorath/sheogorath_memory.json`… relatifs à `Sheogorath/`, alors que les bases vivent
   dans `/app/data`. Elle ignore `decisions.db` et `api_usage.db`.

Aucune ligne `[BACKUP]` dans les journaux de Sheogorath sur 72 h. Les seules sauvegardes
existantes sont trois copies **manuelles** dans `data/` (11/06, 11/09, 13/09), repassées du
mode WAL au mode normal par Claude le 27/09.

Tout repose donc sur **un seul fichier SQLite** (`data/bots_database.db`) partagé par
l'hôte Windows et six conteneurs Linux, plus `decisions.db`, `api_usage.db` et
`dashboard_audit.db`.

---

# LOT 1 — L'outil `tools/sauvegarde_bases.py`

**Bibliothèque standard seulement** (`sqlite3`, `shutil`, `pathlib`, `argparse`, `time`,
`logging`) : il doit tourner dans n'importe quel conteneur Python sans dépendance.

**Ce qu'il sauvegarde**, liste **en dur** :
- les bases `bots_database.db`, `decisions.db`, `api_usage.db`, `dashboard_audit.db` du
  dossier de données ;
- tous les `*.json` du dossier de données (mémoires, faits, configuration, jetons Twitch).

Pas les fichiers `bots_database_backup_*.db` (de vieilles copies), pas les `*.db-journal`.

**Comment** :
- Chaque base est copiée avec l'**API `backup` de SQLite** :
  `src = sqlite3.connect(chemin, timeout=30)`, `dst = sqlite3.connect(cible)`,
  `src.backup(dst)`. C'est la seule copie cohérente quand un bot écrit en même temps ;
  **jamais `shutil.copy` sur une base**.
  - ⚠️ **Ne jamais exécuter `PRAGMA journal_mode`** sur la source : `shared_database.py`
    pose TRUNCATE et c'est voulu (`AGENTS.md`, interdiction 5). L'outil **lit** seulement.
  - Après la copie : `PRAGMA integrity_check` sur la **cible** doit rendre `ok`, et
    `PRAGMA journal_mode` sur la cible ne doit **pas** valoir `wal`. Sinon : supprimer la
    copie, journaliser en `error`, code de sortie ≠ 0.
- Les JSON : `shutil.copy2`.
- Destination : `<dossier de sauvegarde>/AAAA-MM-JJ_HHMM/` (UTC). La copie se fait d'abord
  dans `…_HHMM.partiel/`, renommé à la fin : un dossier sans `.partiel` est toujours complet.

**Quand** : option `--si-plus-vieux-que HEURES` (défaut **20**). L'outil regarde la date
de la sauvegarde **complète** la plus récente ; si elle est plus jeune que ce délai, il ne
fait rien et le dit en une ligne. C'est ce qui permet de l'appeler toutes les heures sans
dépendre de l'heure de démarrage : l'erreur exacte de l'ancienne boucle.

**Rotation** : garder les **14** sauvegardes complètes les plus récentes, supprimer les
plus anciennes, et supprimer tout dossier `.partiel` de plus de 24 h. Ne supprimer **que**
des dossiers dont le nom correspond exactement à `^\d{4}-\d{2}-\d{2}_\d{4}(\.partiel)?$`
([[gotcha-suppression-par-motif-textuel]]).

**Options** : `--donnees` (défaut : `$DATA_DIR`, sinon `data/` à la racine du dépôt),
`--sortie` (**obligatoire**, pas de défaut : une sauvegarde qui tomberait par défaut sur le
disque du projet serait exactement ce qu'on veut éviter), `--si-plus-vieux-que`,
`--boucle` (voir LOT 2). Docstring dans le style des autres outils : pourquoi il existe (le
constat ci-dessus), ce qu'il copie, comment le restaurer (copier le fichier du dossier daté
à la place de celui de `data/`, **bots arrêtés**).

# LOT 2 — Le faire tourner : un service `sauvegarde` dans `docker-compose.yml`

**Mode `--boucle`** : l'outil tourne sans fin, appelle la sauvegarde avec
`--si-plus-vieux-que`, puis dort **une heure** (`time.sleep(3600)`), et recommence. Une
exception pendant un passage est journalisée et n'arrête pas la boucle.

**Service**, à ajouter après `malena` et avant `laya` :

```yaml
  sauvegarde:
    <<: *bot-common
    container_name: bots-sauvegarde
    volumes:
      - ./data:/app/data
      - D:/Sauvegardes/BotDiscord/bases:/app/sauvegardes
      - ./tools/sauvegarde_bases.py:/app/sauvegarde_bases.py:ro
    working_dir: /app
    command: python sauvegarde_bases.py --boucle --donnees /app/data --sortie /app/sauvegardes
    environment:
      - DATA_DIR=/app/data
```

- ⚠️ `./data` **en écriture**, comme pour les bots : SQLite doit pouvoir poser ses verrous
  et, le cas échéant, traiter un journal en attente. Un montage `:ro` peut faire échouer
  l'ouverture.
- Même image que les bots (`build: .`), même durcissement (`cap_drop`, `no-new-privileges`,
  utilisateur non-root) : aucun fichier de bot n'est monté, aucune clé.
- Il n'appartient à aucun bot : chaque bot reste déployable seul, et **aucun bot n'importe
  l'outil**.

- ⚠️ Le chemin `D:/…` n'existe que sur **cette** machine. Le commenter dans le compose :
  « chemin propre à la machine de dev ; sur un autre hôte (Oracle), le remplacer par un
  disque qui n'est PAS celui du projet ».
- Créer le dossier avant de démarrer le service : `D:\Sauvegardes\BotDiscord\bases` et
  `D:\Sauvegardes\BotDiscord\cles`.

**`.gitignore`** : ajouter quand même `/sauvegardes/` (**ancré** par le `/` de tête,
[[gotcha-gitignore-non-ancre]]) dans la section « État de jeu runtime et sauvegardes »
(l.40) : si quelqu'un passe un jour `--sortie sauvegardes`, les **jetons Twitch** des JSON
ne doivent pas pouvoir être commités. Vérifier avec `git check-ignore sauvegardes/x.json`.

# LOT 3 — Retirer la fausse sauvegarde de Sheogorath

Une tâche qui a l'air de sauvegarder et ne sauvegarde rien est pire qu'aucune : elle
rassure à tort.

- `Sheogorath/bot_sheogorath.py` : supprimer la tâche `daily_backup_check` (l.1245–1255,
  décorateur compris) et son démarrage (l.849–850, le `if not daily_backup_check.is_running():`
  et sa ligne). Vérifier ensuite qu'**aucun** `daily_backup_check` ne reste
  (`grep -n daily_backup_check`), puis `pyflakes`.
- `Sheogorath/backup_manager.py` : le supprimer (`git rm`). Vérifié le 28/09 : seul
  `bot_sheogorath.py` l.1252 l'importe. Refaire le `grep -rn "backup_manager"` avant, et
  s'arrêter si un autre fichier l'utilise.
- ⚠️ **Ne pas redémarrer Sheogorath** pour ça : le code mort ne tourne pas, la
  suppression prendra effet au prochain redémarrage normal.

# LOT 3-bis — Les clés : une copie hebdomadaire sur `D:`, faite par l'HÔTE

Aujourd'hui les clés API et tokens Discord des six bots n'existent **que sur `I:`** :
`*/.env.encrypted` + `*/.master_key`. GitHub ne les a pas, et c'est voulu. Perdre `I:`
obligerait à régénérer toutes les clés chez chaque fournisseur, pour les six bots.

**Outil neuf** : `tools/sauvegarde_cles.py`, bibliothèque standard seulement.

- Fichiers copiés, liste **en dur** (pas de glob : un glob `*.env*` emporterait les
  `.env.example` et les `.bak_*`) : pour chacun de `Alfred`, `Sheogorath`, `MaiqBot`,
  `JohnnyBot`, `SugarBot`, `MalenaBot` → `<Bot>/.env.encrypted` et `<Bot>/.master_key` ;
  plus `dashboard/.env`. Un fichier absent est **signalé** (ligne `WARN`), jamais ignoré en
  silence.
- ⚠️ **Lecture seule sur la source** : `shutil.copy2` uniquement. `AGENTS.md` interdit de
  supprimer, écraser ou modifier un `.env` ou un `.master_key` : l'outil ne fait **que**
  lire, et il **refuse** (erreur, code ≠ 0) si `--sortie` se trouve à l'intérieur du dépôt.
- Destination : `<sortie>/AAAA-MM-JJ/<Bot>/…`, même structure que le dépôt. Rotation :
  garder les **8** plus récents, même règle de nom stricte que pour les bases
  (`^\d{4}-\d{2}-\d{2}$`).
- Vérification après copie : chaque fichier copié a la même taille et le même SHA-256 que
  la source. L'outil n'affiche **jamais** le contenu ni l'empreinte complète (8 premiers
  caractères au plus, comme `tools/sonde_cles_partagees.py`).
- Options : `--sortie` (obligatoire), `--si-plus-vieux-que JOURS` (défaut **6**).
- **Pourquoi pas dans le conteneur `bots-sauvegarde`** : il faudrait y monter les douze
  fichiers de clés, un service de plus qui les voit. Sur l'hôte, ils sont déjà là.

**Test** dans `tests/test_sauvegarde_bases.py` (ou un fichier voisin), dans `tmp_path` :
une fausse arborescence avec les 13 fichiers, une copie, les empreintes identiques, les
sources **inchangées** (même mtime, même contenu) ; `--sortie` à l'intérieur de la fausse
racine → refus ; un fichier manquant → `WARN` et code 0.

**[Ahmed] La tâche planifiée Windows** (configuration persistante : c'est à Ahmed de la
créer, pas à l'agent). Commande à lui donner, une ligne, dans un PowerShell :

```
schtasks /Create /TN "BotDiscord - sauvegarde des cles" /SC WEEKLY /D SUN /ST 12:00 /TR "\"I:\IA\Bot Discord\.venv\Scripts\python.exe\" \"I:\IA\Bot Discord\tools\sauvegarde_cles.py\" --sortie D:\Sauvegardes\BotDiscord\cles"
```

Vérifier le chemin exact de `python.exe` du `.venv` avant de la lui donner.

# LOT 4 — Les tests

**Fichier neuf** : `tests/test_sauvegarde_bases.py`. Tout dans `tmp_path`, **jamais** dans
`data/` ([[gotcha-pytest-pollue-data]]).

- une base de test avec une table et 3 lignes, **en mode TRUNCATE**, plus un JSON : après
  une sauvegarde, le dossier daté existe, la base copiée a 3 lignes, `integrity_check` =
  `ok`, `journal_mode` ≠ `wal`, et le JSON est identique ;
- après la sauvegarde, la source n'est **pas** en WAL (`journal_mode` ≠ `wal` à la
  réouverture) et **aucun** fichier `-wal` ni `-shm` n'existe à côté d'elle. ⚠️ Ne pas tester
  « la source est toujours en TRUNCATE » : TRUNCATE est un réglage de CONNEXION, une
  nouvelle connexion lit `delete` quoi qu'il arrive ;
- `--si-plus-vieux-que 20` juste après une sauvegarde : **aucun** nouveau dossier ;
- rotation : avec 16 dossiers datés factices, il en reste 14, les plus récents ; un
  dossier `autre_chose/` dans la sortie n'est **pas** touché ;
- un `.partiel` de plus de 24 h est supprimé ; un `.partiel` récent ne l'est pas ;
- un verrou AST sur `Sheogorath/bot_sheogorath.py` : plus aucun nom `daily_backup_check`
  ni import de `backup_manager` (ne pas laisser la fausse sauvegarde revenir).

# LOT 5 — Livrer et démarrer

1. `python -m pyflakes tools/sauvegarde_bases.py Sheogorath/bot_sheogorath.py tests/test_sauvegarde_bases.py`
2. pytest ciblé, puis complet (**jamais deux pytest en parallèle**, port 8599).
3. Une sauvegarde **à la main**, sur l'hôte, avant le service :
   `python tools/sauvegarde_bases.py --si-plus-vieux-que 0 --sortie D:/Sauvegardes/BotDiscord/bases`.
   Vérifier le dossier daté, les 4 bases (`integrity_check` = `ok`) et les JSON.
4. Commit `feat(sauvegarde): sauvegarde verifiee des bases hors de data/ (SUITE 12)`.
   Push, **`gh run list` jusqu'au vert**.
5. **Démarrer uniquement le nouveau service** : `docker compose up -d --no-deps sauvegarde`.
   ⚠️ **`--no-deps` et le nom du service sont obligatoires** : un `docker compose up -d` sans
   nom recréerait les six bots. Vérifier ensuite avec `docker ps` que les bots ont gardé
   leur heure de démarrage (`docker inspect -f "{{.State.StartedAt}}"`), et que
   `docker logs bots-sauvegarde` dit « sauvegarde récente, rien à faire » (celle de
   l'étape 3 a moins de 20 h). ⚠️ Vérifier aussi que le conteneur, **non-root**, peut ÉCRIRE
   sur `D:` : `docker exec bots-sauvegarde sh -c "touch /app/sauvegardes/.test && rm /app/sauvegardes/.test"`.
6. La copie des clés (LOT 3-bis) une première fois à la main, puis l'étape [Ahmed].

# LOT 6 — [Ahmed] Le lendemain

`dir D:\Sauvegardes\BotDiscord\bases` : un **deuxième** dossier daté est apparu tout seul, environ 20 h après le
premier. `docker logs bots-sauvegarde --since 24h` : une ligne de sauvegarde réussie, zéro
erreur.

**Critère de clôture** : tests et CI verts, service démarré sans avoir touché aux bots,
deux sauvegardes complètes à ~20 h d'écart sur `D:`, une copie des clés sur `D:` et la tâche
planifiée des clés visible dans le Planificateur de tâches.

---

## Hors périmètre (noté, NON planifié)

- **Une copie hors de la machine** : `D:` protège d'une panne du disque `I:`, **pas** d'un
  vol, d'un incendie ou d'un rançongiciel qui toucherait tout le PC. Piste gratuite quand
  Ahmed le voudra : une archive **chiffrée** (7z + mot de passe) sur son Google Drive
  (15 Go gratuits). Jamais sur GitHub, même privé. Décision d'Ahmed.
- Les trois copies manuelles de `data/` (`bots_database_backup_*.db`) peuvent être
  déplacées dans `D:\Sauvegardes\BotDiscord\bases\` une fois le service en place. Décision
  d'Ahmed.
- Les `*/.env.encrypted.bak_*` (une dizaine par bot) : autant de copies des clés, à trier un
  jour. Pas ici : `AGENTS.md` interdit de toucher aux fichiers de clés sans décision d'Ahmed.
