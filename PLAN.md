# PLAN — Remettre en marche le suivi des appels API

> **✅ EXÉCUTÉ le 2026-08-29** — phases A → I dans l'arbre, 432 tests verts, vendoring
> stable, aucune dérive. Vérifié fichier par fichier, pas sur annonce.
> Cinq défauts relevés à la relecture et corrigés au passage :
> 1. traces fantômes — une branche qui ne tourne pas (pas de clé Gemini, client absent)
>    écrivait un échec sans cause → `raison = "pas_de_cle"` / `"non_tentee"` ;
> 2. `reinitialiser_pour_tests()` posait sa pilule **avant** de vider la file → sur file
>    pleine (cas H.5) `put_nowait` levait `Full` et l'écrivain ne s'arrêtait jamais ;
> 3. le helper d'attente des tests guettait `is_alive()` d'un thread démon **toujours
>    vivant** → 25 s de sable, et aucun drainage réellement vérifié ;
> 4. le test H.3 vérifiait que le label brut ressort brut — l'inverse de D1, et il
>    passait déjà avant le chantier. Refait sur la vraie cascade (+ 2 tests) ;
> 5. `get_keys_status` du dashboard avalait son erreur sans un mot (R6), et
>    `api_manager.py` gardait `sqlite3`/`Path`/`deque` morts (phases D et E).
> H.7 était en écart : une seconde `_FauxConnexion` avait été écrite au lieu de
> réutiliser celle de `test_base_partagee`. Corrigé par sous-classe.
>
> **Reste : le déploiement et la vérification réelle (§ PHASE I) — c'est elle le critère.**

> **Destinataire : Antigravity.** Plan d'exécution.
> **État au 2026-08-29 : seule la phase A est dans l'arbre, et elle est fausse.**
> Antigravity a annoncé « plan exécuté » le 2026-08-27 ; vérification faite, le dernier
> commit est toujours `c1b0696` et les phases B→I n'existent pas. Commencer par **A-bis**
> (correctif du fichier déjà écrit), puis B→I. **Vérifier l'arbre, pas l'annonce.**
> **Base de référence : commit `c1b0696`.** Tous les numéros de ligne ci-dessous sont
> pris sur cet état de l'arbre. Chaque ancre est doublée d'un extrait « AVANT » unique :
> **en cas de désaccord entre le numéro et l'extrait, c'est l'extrait qui fait foi.**

---

## 1. Constat (mesuré le 2026-08-27 sur `data/api_usage.db`)

Le point de départ était « durcir la deuxième base partagée comme `a6e8327` a durci la
première ». En ouvrant la base, le problème s'est révélé plus grand que ses réglages
SQLite : **elle n'enregistre presque rien, et ce qu'elle enregistre est faux.**

```
api_calls               : 121 lignes, depuis toujours
dernier appel d'un bot NOMME : 2026-06-13  (johnny)
noms presents           : alfred, johnny, maiq, onizuka, za'ji, unknown
                                             └──────┴── renommes depuis des mois
75 lignes sur 121 sont « unknown », toutes en success=0, derniere le 2026-08-23
api_key_status : gemini -> total_calls=0, total_errors=69
```

Quatre causes, chacune vérifiée dans le code :

| # | Cause | Preuve |
|---|---|---|
| 1 | `track_call` n'est appelé **de nulle part** sur le chemin nominal | son unique appelant est `report_error`, `shared/api_manager.py:206` |
| 2 | `report_error` n'est appelé que pour **`"gemini"`** | `shared/llm_cascade.py:207-209`, idem dans les 6 bots |
| 3 | `bot_name="unknown"` est **écrit en dur** | `shared/api_manager.py:207` |
| 4 | `track_tokens` n'a **aucun appelant** | `grep -rn "track_tokens(" --include="*.py" .` ne rend que la définition |

Conséquence : la base ne peut contenir que des **échecs Gemini anonymes**. Le panneau
`/api/api-usage` du dashboard affiche 0 appel sur 24 h en permanence, et c'est structurel.

**Ce que ça coûte** : c'est exactement l'information qui manquait pendant
`d0dda1c` (cascade par persona). Il a fallu écrire `tools/sonde_modeles_persona.py` et
sonder à la main ce que cette base était censée donner en continu. La question est déjà
revenue trois fois (`3b42e88`, `d0dda1c`, `9af50cd`).

---

## 2. Règles d'exécution — à lire avant la première ligne de code

**R1. `api_manager.py` et `llm_cascade.py` sont vendorisés en 6 copies.** On modifie
**uniquement `shared/`**, puis on lance `python tools/vendor_core.py`. Ne jamais éditer
un fichier sous `<Bot>/core/` : il porte un en-tête « FICHIER GENERE — NE PAS EDITER ».

**R2. La liste des modules vendorisés est DUPLIQUÉE dans deux fichiers.**
`tools/vendor_core.py:6` et `tools/sonde_core_drift.py:6`. Un module ajouté à l'une et
pas à l'autre est copié **sans jamais être surveillé** — la sonde de dérive l'ignore en
silence. **Les deux listes doivent rester identiques.**

**R3. Le réécrivage d'imports ne couvre que les modules listés.** `vendor_core.py:51-52`
ne réécrit `from shared.X` en `from core.X` que pour les `X` de `MODULES`. Un nouveau
module non listé laisserait `from shared.api_tracking` dans les copies → **les bots
perdent leur indépendance** (règle `bots-independants`, décision `1daec85`).
⚠️ **Et la réécriture est ancrée en début de ligne** (`re.MULTILINE`, motif `^from shared\.`).
Un `from shared.api_tracking import tracer_appel` écrit **à l'intérieur d'une fonction**
(donc indenté) n'est **pas** réécrit : il resterait `shared.` dans les 6 copies. Tous les
imports du nouveau module doivent être **en tête de fichier, colonne 0**.
⚠️ Corollaire du gotcha `import asyncio` local (`UnboundLocalError`) : un import posé dans
un corps de fonction rend le nom local à **toute** la fonction. Colonne 0, sans exception.

**R4. La sonde d'appels bloquants ne verra PAS une écriture SQLite.**
`tools/sonde_blocking_calls.py:26` ne surveille que `generate_content`,
`chat.completions.create`, `chat.complete`. Une écriture sqlite synchrone dans une
coroutine gèlerait la boucle **sans qu'aucune sonde ne le dise**. C'est pour ça que la
phase A impose une écriture hors boucle par construction.

**R5. Il y a DEUX cascades.** `shared/llm_cascade.py:generate_response` sert cinq bots ;
**Malena a sa propre cascade inline** : `MalenaBot/bot_malena.py:205`
`generate_response_hybrid`. C'est le piège de `f1fbf72`, où corriger `shared/` n'avait
pas couvert Malena. Phase C n'est pas optionnelle.

**R6. Ne jamais faire échouer un appel LLM à cause de la trace.** Toute erreur
d'enregistrement est avalée — mais **journalisée**, jamais `except: pass`.

---

## 3. Décisions déjà prises (ne pas les rouvrir)

**D1 — Le nom du bot vient de `bot_label`, pas d'une nouvelle configuration.**
`shared/models.py:105 bot_id_depuis_label()` normalise déjà « Johnny Silverhand » →
`"johnny"`, « M'aiq le Menteur » → `"maiq"`. Cette fonction est **déjà** utilisée pour
choisir la cascade (`models.py:122`). `generate_response` reçoit **déjà** `bot_label`
(`llm_cascade.py:61`). Le nom est donc disponible au point de passage, gratuitement, et
il tombera sur les **mêmes clés** que `CASCADES_PERSONA` : `sheo`, `sugar`, `maiq`,
`alfred`, `johnny`, `malena`. Aucun `BOT_NAME` à ajouter au `docker-compose.yml` (il n'y
en a pas aujourd'hui — vérifié).
⚠️ `bot_id_depuis_label` rend **`None`** si aucun marqueur ne correspond (le défaut de
`generate_response` est `bot_label="Bot"`). Repli : garder le **label brut** en minuscules.
Ne jamais réécrire un nom inconnu en `"unknown"` — c'est ce qui a rendu la base illisible.

**D2 — `TRUNCATE` plutôt que `WAL` pour `api_usage.db`.**
Le dashboard lit cette base en **lecture seule** (`api_tracker.py:14`, URI `?mode=ro`).
Un lecteur read-only sur une base WAL exige que le fichier `-shm` existe **et soit
accessible en écriture** — précisément ce que le montage bind Docker/Windows ne sert pas
de façon fiable (`gotcha-sqlite-wal-bind-mount`, `a6e8327`). Ça marche aujourd'hui sur
l'hôte (vérifié le 2026-08-27 : `journal_mode=wal`, lecteur `mode=ro` OK), mais le jour
où ça lâche, le lecteur rend `None` en silence et on ne distingue plus « aucun appel » de
« base injoignable ». TRUNCATE n'a besoin d'aucune mémoire partagée.
⚠️ **La base existante est en WAL** : le mode est une propriété **persistante du
fichier**. Poser TRUNCATE au démarrage suffit à la convertir, mais le vérifier
explicitement en phase I (étape 4).

**D3 — On supprime la machinerie TPM au lieu de la câbler.**
On ne durcit pas une façade. Un compteur que personne n'incrémente donne une fausse
assurance de quota. Les quotas sont déjà tenus par la quarantaine de clés de
`report_error`, qui, elle, fonctionne.

**D4 — On ne touche pas à la quarantaine de clés.**
`report_error` / `is_api_available` / `get_key` : cette logique sert en vrai. On lui
retire seulement son `track_call` parasite (phase D).

---

## PHASE A — Un écrivain unique, hors boucle asyncio

**Nouveau fichier : `shared/api_tracking.py`.**

Un module qui expose **une seule fonction publique** :

```python
tracer_appel(bot, api, modele, index_cle, succes, code_erreur=None,
             latence_ms=None, raison=None) -> None
```

### Conception imposée

- **Non bloquante par construction** : `tracer_appel` **empile dans une
  `queue.Queue`** et rend la main immédiatement. Un **unique thread démon** dépile et
  écrit. Trois problèmes réglés d'un coup :
  1. la boucle asyncio n'est jamais bloquée (R4) — pas besoin d'un `to_thread` chez
     l'appelant, donc rien à ajouter dans la cascade ;
  2. **un seul thread possède la connexion** → le `check_same_thread=False` sans verrou
     de `api_manager.py:45` disparaît de lui-même ;
  3. la file borne l'impact : `Queue(maxsize=1000)`, et **`put_nowait` avec `except
     queue.Full`** → on perd une trace plutôt que de retarder un bot.
- **File pleine** : journaliser **une seule fois** (drapeau de module), pas à chaque
  perte. Motif déjà en place : `shared/shared_database.py:32 _JOURNAL_POSE`.
- **Démarrage paresseux** : le thread démarre à la première trace, pas à l'import (un
  import ne doit rien lancer).
- Thread **démon** : pas de `setup_graceful_shutdown` à modifier. Perdre les quelques
  traces en file à l'arrêt est acceptable ; bloquer un arrêt Docker ne l'est pas.

### La connexion (les 4 défauts SQLite, ici et nulle part ailleurs)

Reprendre le modèle de `shared/shared_database.py:65 get_connection()` :

| défaut actuel (`api_manager.py`) | correction |
|---|---|
| `sqlite3.connect(db_path, check_same_thread=False)` sans verrou (l.45) | connexion possédée par le thread écrivain, `check_same_thread` inutile |
| pas de `timeout=` → 5 s (l.45) | `timeout=20` (busy_timeout 20 s, comme l'autre base) |
| aucun `journal_mode` | `PRAGMA journal_mode=TRUNCATE` (D2), en **vérifiant la valeur rendue** — SQLite peut rendre un autre mode **sans lever** |
| `except Exception: pass` (l.96) | `logger.warning`, **une seule fois** |

Poser aussi `PRAGMA synchronous=NORMAL` dans **son propre `try`** — c'est le défaut
corrigé par `a6e8327` sur l'autre base : mis dans le même `try` que le journal, il
n'était jamais posé dès que le journal échouait.

### Schéma

Réutiliser les tables existantes `api_calls` et `api_key_status`
(`api_manager.py:46-73`) : ne pas les recréer ailleurs, **déplacer** les `CREATE TABLE
IF NOT EXISTS` dans le nouveau module et les retirer de `_init_usage_db`.
Ajouter une colonne `raison TEXT` à `api_calls` via `ALTER TABLE` gardé
(`try/except sqlite3.OperationalError`) — la base existante a 121 lignes qu'on ne
détruit pas.

### ⚠️ Vendoring

`api_tracking.py` doit être ajouté aux **deux** listes `MODULES` (R2) :
`tools/vendor_core.py:6` et `tools/sonde_core_drift.py:6`. Sans ça, R3 casse
l'indépendance des bots. ✅ **Déjà fait** (les deux listes portent `api_tracking.py`,
en 17e position — vérifié le 2026-08-29). Rien à refaire ici.

---

## PHASE A-bis — Corriger `shared/api_tracking.py`, déjà écrit mais faux

Le fichier existe dans l'arbre (non suivi par git, 164 lignes). Sa structure est la
bonne — file + thread démon unique, TRUNCATE vérifié sur la valeur rendue, `synchronous`
dans son propre `try`, `ALTER TABLE` gardé : tout ça est conforme et **ne doit pas être
réécrit**. Mais quatre défauts le rendent muet exactement dans le cas où il devrait parler,
et **font échouer trois des tests de la phase H** tels qu'ils sont spécifiés.

### A-bis.1 — `_get_connection()` est hors du `try` intérieur : le thread meurt en silence

```
AVANT (l. 75-82)
def _writer_loop():
    global _JOURNAL_POSE
    conn = None
    try:
        conn = _get_connection()
        while True:
            try:
                task = _queue.get()
```

Le `try` extérieur n'a **que** `finally`, pas d'`except`. Si la base est illisible
(dossier en lecture seule, disque plein, `-shm` refusé par le bind mount),
`_get_connection()` lève, l'exception traverse `_writer_loop` et part dans
`threading.excepthook` → **stderr, pas `logger`**. Trois conséquences :

1. **R6 n'est pas tenue** : aucune trace journalisée. Le test **H.4** (`caplog`) ne verra
   rien et échouera.
2. `_ensure_thread()` teste `is_alive()` : le thread étant mort, il en **relance un
   neuf à chaque trace**, condamné de la même façon. Sous charge → un thread par appel LLM.
3. La perte est totale et silencieuse, ce qui est le bug d'origine du chantier.

**Correction imposée** : ouvrir la connexion **dans** une zone protégée, journaliser
**une fois** au niveau `warning`, puis **abandonner définitivement** — poser un drapeau
de module (`_ECRIVAIN_HS = True`) que `_ensure_thread()` consulte **avant** de relancer.
Un écrivain qui ne peut pas ouvrir sa base ne s'améliorera pas au 500e essai ; le
contrat est « on perd des traces, on ne gêne jamais un bot » (R6). `tracer_appel` devient
alors un `return` immédiat, pas une relance.

### A-bis.2 — Les erreurs d'écriture sont en `logger.debug` : muettes en production

```
AVANT (l. 113-114)
            except Exception as e:
                logger.debug(f"[API TRACKING] Erreur d'écriture SQLite : {e}")
```

`debug` n'est pas émis avec la configuration des bots. C'est le `except: pass` de
`api_manager.py:96` sous un autre nom — or c'est précisément ce que R6 interdit.
**Correction** : `logger.warning`, **une seule fois**, sur le modèle
`shared/shared_database.py:32 _JOURNAL_POSE`.

⚠️ **Il faut DEUX drapeaux distincts, pas un.** Aujourd'hui `_JOURNAL_POSE` sert déjà à
la file pleine (l. 144 et 162). Le réutiliser pour les erreurs d'écriture ferait qu'une
file pleine **bâillonne** le premier échec d'écriture, et inversement : deux pannes de
nature différente, dont une seule serait jamais vue. Trois drapeaux nommés :
`_JOURNAL_FILE_PLEINE`, `_JOURNAL_ECRITURE`, `_JOURNAL_CONNEXION`.
Au passage, le bloc `except queue.Full` est écrit deux fois à l'identique
(`tracer_appel` l. 141-146, `tracer_etat_cle` l. 159-164) : le factoriser en un
`_empiler(tache)` privé — deux copies dérivent, c'est la leçon de `f1fbf72`.

### A-bis.3 — `task_done()` est sauté sur le chemin d'erreur → la phase H se bloque

```
AVANT (l. 111-114)
                conn.commit()
                _queue.task_done()
            except Exception as e:
```

`task_done()` est la **dernière** instruction du `try` : dès qu'un `INSERT` échoue, il est
sauté. Le compteur interne de la `Queue` ne redescend jamais → **`_queue.join()` bloque
pour toujours**. Ce n'est pas cosmétique : `join()` est la seule façon propre pour le test
**H.6** (« deux threads qui tracent ne perdent aucune ligne ») d'attendre le drainage sans
`sleep` arbitraire. Le pill d'arrêt (l. 83-84, `break`) le saute aussi.
**Correction** : `task_done()` dans un `finally` de l'itération, appelé sur **tous** les
chemins dès qu'un `get()` a rendu quelque chose.

### A-bis.4 — L'état de module n'est pas réinitialisable : la phase H ne peut pas s'écrire

`_queue`, `_writer_thread` et les drapeaux sont construits à l'import. Les tests H.4, H.5
et H.7 ont besoin de repartir propre (file vide, drapeaux baissés, thread arrêté, nouveau
`DATA_DIR`) — sinon un test qui remplit la file (H.5) rend muets tous les suivants, et
l'ordre de collecte de pytest décide du résultat.

**Ajouter une fonction publique `reinitialiser_pour_tests()`** : arrête l'écrivain
(pill), vide la file, remet les trois drapeaux à `False` et `_ECRIVAIN_HS` à `False`.
Elle est appelée **uniquement** par `tests/test_suivi_api.py` (fixture `autouse`), jamais
par un bot. C'est le seul ajout d'API autorisé : le module garde ses **deux** fonctions
métier, `tracer_appel` et `tracer_etat_cle`.

### Ce qu'il ne faut PAS changer en passant

- Le schéma des tables (l. 36-70) est conforme à la phase A : il réutilise les tables
  existantes et l'`ALTER TABLE` gardé. **Ne pas détruire les 121 lignes existantes.**
- `PRAGMA journal_mode=TRUNCATE` avec vérification de la valeur rendue (l. 24-26) est
  exactement ce que D2 demande. Ne pas le « simplifier ».
- `synchronous` est bien dans son propre `try` (l. 30-33) — c'est le défaut corrigé par
  `a6e8327`, verrouillé par le test H.8. Ne pas le refusionner.
- `check_same_thread` reste absent : un seul thread possède la connexion. C'est le point.

---

## PHASE B — Brancher au point de passage unique

**Fichier : `shared/llm_cascade.py`, fonction `generate_response`.**

Le point de passage est **le corps de la boucle** `for client_type, model_name in
cascade:` (l. 86), **pas** les ~10 sites de `break`/`continue`.

### Mécanique imposée : `try/finally` par itération

Un `finally` s'exécute sur `break`, sur `continue` **et** sur exception : une trace par
tentative de branche, sans toucher aux sorties.

⚠️ **`time` n'est pas importé dans `shared/llm_cascade.py`** (vérifié : imports l. 5-13,
`asyncio`, `base64`, `logging` seulement). Ajouter `import time` **en tête de fichier,
colonne 0** — jamais dans le corps de `generate_response` (R3, gotcha `UnboundLocalError`).

```
AVANT (l. 86-87)
    for client_type, model_name in cascade:
        try:

APRES
    for client_type, model_name in cascade:
        _depart = time.perf_counter()
        _code_erreur = None
        _raison = None
        try:
          try:
```
…et le `finally` correspondant se referme après le `except Exception as e:` existant
(l. 205-210), en appelant `tracer_appel(...)`.

**Le succès se déduit de `response_text`, sans toucher aux branches.** Vérifié : toute
sortie qui laisse `response_text` non vide fait un `break` ; toutes les branches d'échec
le remettent à `None` avant de continuer (l. 120, 151, 171, 195, 200). Donc
`succes = bool(response_text)` dans le `finally` est fidèle.
⚠️ `response_text` est une variable de **fonction**, pas d'itération (initialisée l. 79).
Le raisonnement ci-dessus tient parce que toute branche d'échec la réinitialise — **ne
pas casser cette propriété** en ajoutant une branche qui l'oublierait.

**La raison de l'échec**, elle, demande 6 affectations d'une ligne, aux endroits qui
émettent déjà un `logger.warning` :

| ligne | contexte | poser |
|---|---|---|
| 119-120 | Gemini réponse vide | `_raison = "vide"` |
| 150-151 | Mistral réponse vide | `_raison = "vide"` |
| 170-171 | Groq réponse vide | `_raison = "vide"` |
| 193-195 | OpenRouter fuite de raisonnement | `_raison = "fuite_raisonnement"` |
| 198-200 | OpenRouter réponse vide | `_raison = "vide"` |
| 205-206 | exception | `_raison = type(e).__name__` |

Ces motifs-là sont précisément ceux qui ont coûté `f1fbf72` et `ff0ecd2` : les compter
est tout l'intérêt du chantier.

**Le code d'erreur** : l'expression existe déjà l. 208
(`getattr(e, 'code', getattr(e, 'status_code', 0))`), aujourd'hui calculée **seulement
pour Gemini**. La sortir du `if client_type == "gemini"` pour la calculer sur toute
exception, et la mettre dans `_code_erreur`. **Ne pas déplacer** l'appel à
`key_manager.report_error`, qui doit rester réservé à Gemini (D4).

**Le nom du bot** : `bot_id_depuis_label(bot_label) or (bot_label or "").lower()` (D1).
Importer depuis `shared.models` — déjà importé l. 13, compléter la ligne d'import.

**L'index de clé** : `api_key` n'existe que dans la branche Gemini (l. 90) et **fuit
d'une itération à l'autre** (c'est déjà le cas aujourd'hui l. 207, un bug latent).
L'initialiser à `None` **au début de chaque itération** et ne passer un index que pour
Gemini. Ne pas écrire la clé elle-même dans la base — **jamais de secret en base**.

---

## PHASE C — Malena (R5)

**Fichier : `MalenaBot/bot_malena.py`, `generate_response_hybrid` (l. 205-340).**

Même mécanique : `try/finally` par itération autour de la boucle l. 211
(`for client_type, model_name in cascade:`), `finally` après le `except Exception as e:`
l. **336** (numéro revérifié le 2026-08-29 ; le plan disait 335).
⚠️ **`time` n'est pas importé non plus dans `bot_malena.py`** : `import time` en tête,
colonne 0.

⚠️ **Différence structurelle** : Malena fait `return texte` sur succès — **trois** sites
revérifiés : l. **273**, **297** et **334** au lieu de `break`. Le `finally` s'exécute quand même —
mais **`response_text` n'existe pas** ici : la variable locale est `texte`, et elle n'est
pas partagée entre branches. Il faut donc une variable d'itération dédiée
(`_texte_branche`), posée dans chaque branche juste avant le `return`.

**Appeler la même fonction `tracer_appel` que la phase B.** Pas une adaptation, pas une
copie : l'import passe par `core.api_tracking` (Malena importe déjà son noyau en
`from core.*`, cf. l. 22 et 144). Deux implémentations dériveront — c'est exactement ce
qui a produit `f1fbf72`.

Le nom du bot est ici constant : `"malena"` (déjà écrit en dur l. 209 pour la cascade).

---

## PHASE D — Retirer l'écrivain parasite

**Fichier : `shared/api_manager.py`.**

1. **Supprimer l'appel `self.track_call(...)` dans `report_error`** — bloc l. 200-212,
   depuis le commentaire `# Tracking de l'erreur` jusqu'à la parenthèse fermante. C'est
   la source des 75 lignes `unknown`, et la phase B enregistre désormais le même
   événement, avec le bon nom et la bonne API.
   ⚠️ Le calcul de `key_index` juste au-dessus (l. 201-205) est **encore utilisé** par la
   synchronisation `api_key_status` l. 214. **Ne pas le supprimer avec.**
2. **Supprimer la méthode `track_call`** (l. 78-97) : plus aucun appelant après le
   point 1. Vérifier par `grep -rn "track_call" --include="*.py" .` — ne doivent rester
   que les 6 copies vendorisées, qui disparaîtront à la phase G.
3. **`_init_usage_db`** (l. 39-76) : les `CREATE TABLE` partent en phase A.
   La synchronisation `api_key_status` de `report_error` (l. 214-234) **reste**, mais elle
   doit passer par la connexion du nouveau module, pas par `self._usage_db`.
   → Exposer dans `api_tracking.py` une seconde fonction publique
   `tracer_etat_cle(api, index_cle, valide, cooldown_iso, erreur)` qui emprunte la **même
   file** et le **même thread écrivain**. Après quoi `self._usage_db` et `_init_usage_db`
   n'ont plus de raison d'être : les supprimer, ainsi que `import sqlite3` et
   `from pathlib import Path` s'ils deviennent inutilisés (`py_compile` ne le dira pas).

---

## PHASE E — Retirer le code TPM mort (D3)

**Fichier : `shared/api_manager.py`.** Supprimer :

- `self._tpm_windows = {}` (l. 27)
- `self.TPM_LIMITS = {...}` (l. 28-32)
- `self.TPM_ALERT_THRESHOLD` (l. 33), `self.TPM_PAUSE_THRESHOLD` (l. 34)
- la méthode `track_tokens` entière (l. 146-176)
- `from collections import deque` (l. 6) s'il devient inutilisé

**Vérification préalable obligatoire**, avant de supprimer quoi que ce soit :

```
grep -rn "track_tokens\|TPM_LIMITS\|TPM_ALERT\|TPM_PAUSE\|_tpm_windows" \
     --include="*.py" . | grep -v __pycache__ | grep -v "/core/" | grep -v "\.venv"
```
Doit ne rendre que `shared/api_manager.py`. **Si un appelant apparaît, s'arrêter et le
signaler** au lieu de supprimer.

---

## PHASE F — Rendre le lecteur du dashboard bavard

**Fichier : `dashboard/backend/api_tracker.py`, `_get_connection` (l. 8-21).**

Aujourd'hui : `print()` puis `return None`. Le panneau affiche des zéros, et rien ne
distingue « aucun appel » de « base illisible » (D2).

- remplacer le `print` par un `logger` (module `logging`, comme le reste du backend) ;
- distinguer les deux cas dans le retour : base **absente** (normale au premier
  démarrage) vs base **illisible** (anomalie) ;
- les méthodes `get_usage` / `get_keys_status` doivent pouvoir remonter cet état au
  frontend plutôt que de renvoyer un zéro indiscernable.

⚠️ **Ne pas passer le lecteur en lecture-écriture** pour contourner un problème WAL : le
dashboard tourne sur l'hôte, les bots dans des conteneurs, et le `?mode=ro` est ce qui
garantit qu'un bug de dashboard ne corrompt pas la base des bots. D2 règle le problème
par le mode de journalisation, pas par les permissions.

---

## PHASE G — Vendoring

```
python tools/vendor_core.py
python tools/sonde_core_drift.py
git diff --stat -- '*/core/'
```

Attendu : `api_manager.py`, `llm_cascade.py` **et** `api_tracking.py` modifiés/créés dans
les **6** dossiers `<Bot>/core/`. Si `api_tracking.py` n'apparaît pas → R2 non appliquée.

Puis vérifier l'indépendance, qui est la raison d'être de tout ça :

```
grep -rn "from shared\." */core/
```
Doit ne rien rendre.

---

## PHASE H — Le filet

**Nouveau fichier : `tests/test_suivi_api.py`.** Chaque test doit échouer sur le code
d'avant — sinon il ne verrouille rien.

1. **Un succès produit une ligne** avec `success=1`, le bon `bot_name`, la bonne
   `api_name` et le bon `model`. *(Défaut 1 : impossible aujourd'hui.)*
2. **Un échec Mistral/Groq produit une ligne.** *(Défaut 2 : seul Gemini remontait.)*
3. **Le nom du bot est réel**, pas `"unknown"` — y compris depuis un label non normalisé
   comme `"Johnny Silverhand"`. *(Défaut 3.)*
4. **Une écriture impossible** (base en lecture seule, ou dossier inaccessible)
   **ne fait pas échouer l'appel LLM** et **laisse une trace dans les logs** (R6) —
   tester les deux moitiés, `caplog` pour la seconde.
5. **La file pleine ne bloque pas l'appelant** : remplir la `Queue`, vérifier que
   `tracer_appel` rend la main sans lever et journalise **une seule fois**.
6. **Deux threads qui tracent en même temps ne perdent aucune ligne** — sinon la
   phase A.2 est décorative.
7. **WAL indisponible → repli TRUNCATE explicite**, et **mode vérifié sur la valeur
   rendue** (SQLite ne lève pas toujours). ⚠️ **Réutiliser la `_FauxConnexion` de
   `tests/test_base_partagee.py:25`**, ne pas en réécrire une seconde.
8. **`synchronous` n'est pas dans le même `try` que le journal** — même test que
   `tests/test_base_partagee.py:120`, adapté au nouveau module.
9. **Malena appelle la même fonction que la cascade partagée** : test statique sur les
   sources, dans l'esprit de `f1fbf72`. Vérifier que `bot_malena.py` importe
   `tracer_appel` et n'a pas sa propre écriture SQLite.
10. **Le code TPM a bien disparu** : `track_tokens`, `TPM_LIMITS` absents de
    `shared/api_manager.py`. *(Empêche la résurrection silencieuse au prochain merge.)*
11. **Une base impossible à ouvrir ne fait pas naître un thread par trace** (A-bis.1) :
    après un premier échec de connexion, 50 `tracer_appel` d'affilée laissent
    `threading.active_count()` stable, et le `warning` n'apparaît **qu'une fois**.
12. **`_queue.join()` rend la main même quand un `INSERT` échoue** (A-bis.3) : sans le
    `task_done()` en `finally`, ce test **pend** — le lancer avec un timeout, pas en nu.

**Fixture obligatoire** : un `@pytest.fixture(autouse=True)` qui appelle
`reinitialiser_pour_tests()` **avant et après** chaque test (A-bis.4). Sans elle, H.5
(file pleine) rend muets tous les tests collectés après lui et le résultat dépend de
l'ordre de collecte.

**Ne pas polluer `logs/`** : `plan-pytest-logs-et-pont-v2` — pytest sur l'hôte écrit dans
les mêmes dossiers que le dashboard et fabrique de fausses « erreurs » dans l'interface.
Écrire dans `tmp_path`, jamais dans `data/` ni `logs/`.

**Ne pas écrire dans la vraie `data/api_usage.db`.** Le module lit `DATA_DIR` de
l'environnement (`api_manager.py:42`) : `monkeypatch.setenv("DATA_DIR", str(tmp_path))`.

---

## PHASE I — Vérification et déploiement

### En local, dans cet ordre

```
python -m py_compile */bot_*.py */core/*.py shared/*.py tools/*.py dashboard/backend/*.py
python tools/sonde_blocking_calls.py      # doit rester a 0 probleme
python tools/sonde_core_drift.py          # No drift detected
python tools/vendor_core.py && git diff --exit-code -- '*/core/'
$env:DASHBOARD_RELANCE_SANS_CONSOLE=1; python -m pytest -q
```

### Puis pousser et **regarder la CI**

```
gh run list --repo LeDev/Bot-Discord --limit 3
gh run watch <id> --repo LeDev/Bot-Discord --exit-status
```
`gh` est installé et authentifié depuis le 2026-08-27. La CI a été **rouge pendant cinq
commits** sans que personne ne regarde (`c1b0696`) — ne pas refaire ça.

### Déploiement

```
docker compose restart
```
⚠️ Bind mount : pas besoin de `--build`. Mais **un conteneur déjà `Up` tourne l'ancien
code en mémoire** — le `restart` est obligatoire (`decision-independance-stricte-vendoring-core`).

### Vérification réelle — c'est ELLE le critère de réussite

Les tests passaient déjà pendant les mois où la base ne recevait rien. Après quelques
échanges sur les 6 bots :

```python
import sqlite3
c = sqlite3.connect("data/api_usage.db")
print(c.execute("PRAGMA journal_mode;").fetchone())          # attendu : truncate (D2)
print(c.execute("SELECT bot_name, api_name, success, COUNT(*) FROM api_calls "
                "WHERE timestamp > datetime('now','-1 hour') "
                "GROUP BY 1,2,3").fetchall())
```

Attendu, et **rien de moins** :
1. les **six** noms de bots présents — `malena` incluse (c'est le test de la phase C) ;
2. des lignes `success=1` — impossible avant ce chantier ;
3. des `api_name` autres que `gemini` ;
4. `journal_mode = truncate` ;
5. le panneau API du dashboard affiche autre chose que 0.

Si `malena` manque alors que les cinq autres sont là : la phase C n'a pas pris, ce n'est
pas un bot silencieux.

---

## 4. Récapitulatif des fichiers touchés

| fichier | phase | nature |
|---|---|---|
| `shared/api_tracking.py` | A | **créé, dans l'arbre** — non suivi par git |
| `shared/api_tracking.py` | **A-bis** | **4 correctifs** : connexion, `warning`, `task_done`, reset |
| `tools/vendor_core.py` | A | ✅ fait (+`api_tracking.py`, l. 17) |
| `tools/sonde_core_drift.py` | A | ✅ fait (+`api_tracking.py`, l. 17) — **R2** |
| `shared/llm_cascade.py` | B | `try/finally` + 6 affectations `_raison` |
| `MalenaBot/bot_malena.py` | C | idem, variante `return` |
| `shared/api_manager.py` | D, E | suppressions |
| `dashboard/backend/api_tracker.py` | F | logger + état lisible |
| `*/core/*.py` | G | **généré**, ne jamais éditer à la main |
| `tests/test_suivi_api.py` | H | **création** |

## 5. Ordre de bataille

**A-bis** d'abord (le fichier existe, il faut le rendre honnête), puis **B → C** ensemble
(l'écrivain n'a de sens qu'avec ses appelants, et inversement), puis D → E, puis
G → H → I. **F est autonome** : livrable seul si le reste devait s'arrêter.

⚠️ **Ne pas annoncer « plan exécuté » sans preuve.** À la fin, coller la sortie réelle de :
`git status --short`, `python -m pytest -q` (dernier bloc), et
`grep -rn "tracer_appel" --include="*.py" shared/ MalenaBot/ | grep -v __pycache__`.
Le 2026-08-27, l'annonce a été faite alors que **seule la phase A** existait.

## 6. Hors périmètre — noté, pas à faire ici

- **Fusionner la cascade inline de Malena dans `shared/`.** Elle a déjà coûté `f1fbf72`
  et coûte une réplication ici. Chantier distinct, à ne pas mélanger.
- Le tas de fiches « Reste : test live » qui traînent depuis des semaines.
- Les voix (Sheo `gpt-oss-120b`, Sugar `gemini-3.5-flash-lite`) : **parquées** à la
  demande du 2026-08-27. La phase B donnera la mesure qui manquait pour les juger.
- Documenter le panneau API dans `README.md` : possible, mais ⚠️ `tests/test_documentation.py`
  interdit de recopier un identifiant de modèle dans la doc.
