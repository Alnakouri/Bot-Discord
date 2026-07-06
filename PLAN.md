# PLAN — Renommage technique complet : Onizuka → Sugar Bot

## Objectif
Renommer **entièrement** le bot « Onizuka » (déjà vidé de sa personnalité, ardoise neutre,
commits `0f42fc1` + `0060242`) en **« Sugar Bot »**, y compris **toute l'infrastructure** :
dossier, fichiers, identifiant technique, service Docker, dashboard, config, données runtime.

### Conventions de nommage (à appliquer PARTOUT, sans exception)
| Rôle | Ancien | Nouveau |
|------|--------|---------|
| Identifiant technique (clé config, bot_id, logger, domaine mémoire) | `onizuka` | `sugar` |
| Nom affiché (label, bannières, dashboard, Discord) | `Onizuka` | `Sugar Bot` |
| Dossier du bot | `OnizukaBot/` | `SugarBot/` |
| Fichier principal | `bot_onizuka.py` | `bot_sugar.py` |
| Fichier données persona | `onizuka_data.py` | `sugar_data.py` |
| Fichier mémoire | `onizuka_memory.py` | `sugar_memory.py` |
| Launcher | `start_onizuka.bat` | `start_sugar.bat` |
| Service Docker | `onizuka` / `bot-onizuka` | `sugar` / `bot-sugar` |
| Wing mempalace | `onizukabot` | `sugarbot` |

> **Règle d'or** : `sugar` en minuscules pour tout identifiant/clé/chemin ; `Sugar Bot` pour
> tout texte destiné à l'affichage humain. Ne PAS réintroduire de personnalité — c'est un
> pur renommage d'une ardoise neutre.

> **Utiliser `git mv`** pour tous les déplacements/renommages de fichiers (préserve l'historique).

---

## ⚠️ POINTS CRITIQUES (à lire avant de commencer)

1. **Chiffrement — AUCUNE ré-encryption.** La clé est lue depuis le fichier `OnizukaBot/.master_key`
   (pas dérivée du nom du dossier). Il faut **déplacer `.master_key` ET `.env.encrypted` avec le
   dossier** (`git mv OnizukaBot SugarBot` les emporte). Le `.env.encrypted` restera déchiffrable
   tel quel. **Ne PAS lancer `crypto_utils.py generate`** (écraserait la clé → .env illisible).
2. **Renommage du compte Discord = MANUEL.** Le nom affiché dans le serveur (`bot.user.name`) se
   change dans le **Discord Developer Portal** (application → nom), pas dans le code. Le code ne
   pilote que le `bot_label` (logs/prompts) et la bio via `edit_application`. → étape hors-code,
   à signaler au user.
3. **Données runtime = déplacées, pas re-créées.** Les mémoires/facts existants sont conservés en
   renommant les fichiers et les clés de config (voir §5). Ne rien vider.
4. **Gotcha historique** : par le passé un mélange de secrets `zaji`↔`OnizukaBot` a eu lieu
   (cf. mémoire). Vérifier après coup que `SugarBot/.env.encrypted` déchiffre bien le BON token.

---

## FICHIER PAR FICHIER

### 1. Renommage des fichiers/dossiers (`git mv`)
```
git mv OnizukaBot SugarBot
git mv SugarBot/bot_onizuka.py      SugarBot/bot_sugar.py
git mv SugarBot/onizuka_data.py     SugarBot/sugar_data.py
git mv SugarBot/onizuka_memory.py   SugarBot/sugar_memory.py
git mv SugarBot/start_onizuka.bat   SugarBot/start_sugar.bat
git mv SugarBot/onizuka_data.json   SugarBot/sugar_data.json      # si suivi par git
```
- Fichiers de données non suivis (facts/memory locaux) : renommer aussi sur disque
  (`onizuka_facts.json`→`sugar_facts.json`, `onizuka_memory.json`→`sugar_memory.json`).
- `SugarBot/.master_key`, `SugarBot/.env.encrypted`, `SugarBot/mempalace.yaml`,
  `SugarBot/README.md`, `SugarBot/.env.example`, `SugarBot/games_persona.py` : **suivent le dossier**,
  on édite leur CONTENU plus bas (pas de renommage de nom).

### 2. `SugarBot/bot_sugar.py` (ex-`bot_onizuka.py`) — 70 occurrences
- l.38/40 `setup_logger("onizuka")` / `getLogger("onizuka")` → `"sugar"`.
- l.45 `DATA_FILE = ... "onizuka_data.json"` → `"sugar_data.json"`.
- l.151-153 `from onizuka_memory import ...` / `from OnizukaBot.onizuka_memory import ...`
  → `from sugar_memory import ...` / `from SugarBot.sugar_memory import ...`.
- l.154-155 `onizuka_facts_file` / `onizuka_memory_file` base names → `sugar_facts.json` /
  `sugar_memory.json` (renommer aussi les variables `onizuka_*_file`→`sugar_*_file` par cohérence).
- l.211 `bot_id="onizuka", bot_label="Onizuka"` → `bot_id="sugar", bot_label="Sugar Bot"`.
- l.166, 231, 276 & tout `bot_label="Onizuka"` / `setup_slash_commands(bot, "Onizuka")` /
  `"Onizuka"` de label → `"Sugar Bot"`.
- l.273 `setup_twitch_announcer(bot, "onizuka", ...)` → `"sugar"`.
- Import persona en tête (`from onizuka_data import ...` / `from OnizukaBot.onizuka_data import ...`,
  + `PERSONA`, `PERSONALITY_PROMPT`) → `sugar_data` / `SugarBot.sugar_data`.
- l.491 détection webhook `["onizuka"]` → `["sugar", "sugar bot"]`.
- l.515 `ONIZUKA_NAMES = ["onizuka"]` → renommer var `SUGAR_NAMES = ["sugar", "sugar bot"]`
  (et ses usages).
- Toutes les bannières/logs `on_ready` « Onizuka est en ligne / prêt », « STATISTIQUES ONIZUKA »,
  `[GAMES] … pour Onizuka` → `Sugar Bot`.
- `loop`/fonctions suffixées `_onizuka` (`status_loop_onizuka`, `daily_bio_loop_onizuka`, …) →
  suffixe `_sugar` (renommer déclaration ET appels `.start()`/`.is_running()`).
- Variable globale `onizuka_data` (le dict de compteurs) → `sugar_data` (attention : ne pas
  confondre avec le module `sugar_data` ; préférer `sugar_stats` si collision — au choix d'Antigravity,
  du moment que c'est cohérent et compile).

### 3. `SugarBot/sugar_data.py` (ex-`onizuka_data.py`)
- Docstring/commentaires « Onizuka » → « Sugar Bot ». Contenu déjà neutre (ne pas ré-ajouter de persona).
- `PERSONA["name"]` s'il existe ici : `"Sugar Bot"`. (Sinon voir games_persona.py.)

### 4. `SugarBot/sugar_memory.py` (ex-`onizuka_memory.py`)
- Commentaires « Onizuka » → « Sugar Bot ». Logique inchangée.

### 5. Données runtime dans `data/` (migration — conserver le contenu)
```
git mv data/onizuka_memory.json          data/sugar_memory.json          # si suivi
git mv data/onizuka_facts.json           data/sugar_facts.json
git mv data/onizuka_memory_archive.jsonl data/sugar_memory_archive.jsonl
git mv data/discord_bio_onizuka.json     data/discord_bio_sugar.json
```
(les fichiers non suivis par git : renommer sur disque.)
- `data/twitch_config.json` l.107 : clé `"onizuka"` → `"sugar"` (renommer la CLÉ, garder la valeur).
- `data/bot_features.json` l.14 : clé `"onizuka"` → `"sugar"`.

### 6. `crypto_utils.py`
- l.46 `BOT_DIRS = [... "OnizukaBot" ...]` → `"SugarBot"`.

### 7. `docker-compose.yml` (bloc l.79-89)
- `onizuka:` → `sugar:`
- `container_name: bot-onizuka` → `bot-sugar`
- `- ./OnizukaBot:/app/bot:ro` → `- ./SugarBot:/app/bot:ro`
- `- ./OnizukaBot/.master_key:/app/bot/.master_key:ro` → `- ./SugarBot/.master_key:...`
- `command: python bot_onizuka.py` → `command: python bot_sugar.py`

### 8. Dashboard
- `dashboard/backend/bot_manager.py` l.39-44 : clé `"onizuka"`→`"sugar"`, `"name": "onizuka"`→`"sugar"`,
  `"display": "Onizuka"`→`"Sugar Bot"`, `"dir": "OnizukaBot"`→`"SugarBot"`,
  `"script": "bot_onizuka.py"`→`"bot_sugar.py"`, `"bat": "start_onizuka.bat"`→`"start_sugar.bat"`.
- `dashboard/frontend/js/app.js` l.521 : `"onizuka": { name: "onizuka", display: "Onizuka", color:"#0ea5e9" }`
  → `"sugar": { name: "sugar", display: "Sugar Bot", color: "#0ea5e9" }` (garder la couleur).
- `dashboard/frontend/js/app.js` l.668 : `onizuka: "Onizuka"` → `sugar: "Sugar Bot"`.
- `dashboard/frontend/js/charts.js` l.91 : label `'Onizuka'` → `'Sugar Bot'` (⚠ garder l'ORDRE des
  labels aligné sur l'ordre des données ; ne changer que le texte).
- `dashboard/frontend/index.html` l.152 : `<option value="onizuka">Onizuka</option>`
  → `<option value="sugar">Sugar Bot</option>`.

### 9. Anti-boucle inter-bots (listes de noms — IMPORTANT pour le runtime)
- `shared/twitch_chat.py` l.220 : `["sheo","maiq","johnny","onizuka","malena","alfred"]`
  → remplacer `"onizuka"` par `"sugar"`.
- `Sheogorath/bot_sheogorath.py` l.48 `OTHER_BOT_NAMES` : remplacer `"onizuka", "eikichi"` par
  `"sugar", "sugar bot"` (retire aussi le résidu `eikichi`).

### 10. Modules partagés keyés par bot-id
- `shared/server_events.py` : clé `"onizuka"` (WELCOME/GOODBYE/BIRTHDAY) → `"sugar"` (garder textes neutres).
- `shared/twitch/sanitize.py` : bloc `"onizuka"` → clé `"sugar"`.
- `Sheogorath/sheo_imposter.py` : entrée `"Onizuka"` → `"Sugar Bot"` (prompt déjà neutre).

### 11. Launchers `.bat`
- `Menu_Launcher.bat` l.15 `[4] Lancer Eikichi Onizuka` → `[4] Lancer Sugar Bot` ;
  l.58-59 & l.83 : « Onizuka » → « Sugar Bot », `cd .../OnizukaBot` → `.../SugarBot`,
  `python bot_onizuka.py` → `python bot_sugar.py`, titre `"Onizuka Bot"` → `"Sugar Bot"`.
- `start_all_bots.bat` l.7/26-28 : idem (« Eikichi Onizuka »/« Onizuka » → « Sugar Bot »,
  dossier + script + titre).
- `SugarBot/start_sugar.bat` (ex-start_onizuka.bat) : titre + bannières + `python bot_sugar.py`.

### 12. mempalace (mémoire projet MCP)
- `mempalace.yaml` l.68-72 : `name: onizukabot` + domaines `onizukabot` → `sugarbot`.
- `SugarBot/mempalace.yaml` l.1 : `wing: onizukabot` → `wing: sugarbot`.

### 13. Harnais d'éval
- `tests/eval/persona_loader.py` l.19 : `"onizuka": ("OnizukaBot.onizuka_data", "PERSONALITY_PROMPT", "Onizuka")`
  → `"sugar": ("SugarBot.sugar_data", "PERSONALITY_PROMPT", "Sugar Bot")`.
- `tests/eval/run_eval.py` l.19 : `"onizuka"` → `"sugar"` dans la liste `BOTS`.
- `tests/eval/scenarios.json` : `"onizuka"` → `"sugar"` (clés de scénario).
- `tests/eval/reports/*.json` : **NE PAS toucher** (rapports historiques figés).

### 14. `SugarBot/README.md` + docs
- `SugarBot/README.md` : « Onizuka » → « Sugar Bot » partout (12 occ.), noms de fichiers/dossier MAJ.
- `README.md` (racine) l.13 tableau : `Onizuka` → `Sugar Bot`, chemin `OnizukaBot` → `SugarBot`.
- `ARCHITECTURE.md` (5), `COMMANDES.md` (4), `DEV_GUIDE.md` (1), `MAINTENANCE.md` (1), `AGENTS.md` (1) :
  remplacer `Onizuka`/`OnizukaBot`/`bot_onizuka.py`/`onizuka` selon le contexte (affichage vs technique).

### 15. `SugarBot/.env.example`
- En-tête « ONIZUKA BOT » → « SUGAR BOT » ; placeholders `GEMINI_KEY_ONIZUKA_*` → `..._SUGAR_*`
  (cosmétique, ce sont des exemples).

---

## HORS PÉRIMÈTRE (à NE PAS toucher)

- **Mémoire des AUTRES bots** mentionnant « onizuka » (ce sont des DONNÉES d'autres bots, cf. la
  logique « Option 2 » du plan de vidage) : `Alfred/alfred_memory.json`, `data/johnny_facts.json`,
  `JohnnyBot/johnny_facts.json`, `data/onizuka_facts.json` (⚠ à distinguer : c'est celui d'un
  autre contexte ? vérifier ; si c'est bien la mémoire de Sugar il migre en §5), et
  `migrations/002_migration.py` (succès `gto_disciple`). → laisser tel quel sauf demande explicite.
- `.claude/settings.local.json` (17 occ.) : chemins d'autorisation locaux — cosmétique, non-runtime.
  Régénéré à l'usage → laisser.
- `.obsidian/workspace.json` : état de l'éditeur → laisser.
- `JohnnyBot/johnny_data.py` : liste de passants (contexte narratif d'un autre bot) → laisser.

---

## VÉRIFICATION (après exécution)

1. **`py_compile`** :
   `.venv/Scripts/python -m py_compile SugarBot/bot_sugar.py SugarBot/sugar_data.py SugarBot/sugar_memory.py SugarBot/games_persona.py crypto_utils.py shared/server_events.py shared/twitch/sanitize.py Sheogorath/sheo_imposter.py Sheogorath/bot_sheogorath.py shared/twitch_chat.py dashboard/backend/bot_manager.py tests/eval/persona_loader.py tests/eval/run_eval.py`
2. **Aucun fichier/dossier `onizuka` résiduel** :
   `find . -iname "*onizuka*" -not -path "*/logs/*" -not -path "*/__pycache__/*" -not -path "*/.git/*"`
   → attendu : **0** (hors mémoires d'autres bots laissées hors périmètre §HORS-PÉRIMÈTRE).
3. **Grep identifiant technique résiduel** (hors data d'autres bots, logs, eval reports, settings.local) :
   `grep -rinE "onizuka|eikichi" SugarBot shared Sheogorath dashboard docker-compose.yml crypto_utils.py *.bat *.md mempalace.yaml tests/eval/*.py tests/eval/scenarios.json`
   → attendu : **0**.
4. **Cohérence config** : `data/twitch_config.json` et `data/bot_features.json` contiennent la clé
   `"sugar"` (plus `"onizuka"`).
5. **Déchiffrement OK** (le point le plus risqué) :
   `.venv/Scripts/python crypto_utils.py decrypt` doit régénérer `SugarBot/.env` sans erreur, PUIS
   `.venv/Scripts/python crypto_utils.py encrypt` pour re-verrouiller. Vérifier que le token déchiffré
   est bien celui d'Onizuka/Sugar (pas d'un autre bot).
6. **Import mémoire** :
   `python -c "import sys; sys.path.insert(0,'SugarBot'); import sugar_data, sugar_memory; print('imports OK')"`
7. **Dashboard** : au lancement, l'entrée « Sugar Bot » apparaît (id `sugar`), le sélecteur et les
   graphes n'ont plus « Onizuka ».
8. **Test live** (skill `verify` ou manuel) : `bot_sugar.py` démarre, `on_ready` affiche « Sugar Bot
   est en ligne », une mention simple → réponse neutre, `!jackpot`/`!exploit`/`!fric` ne plantent pas,
   pas de boucle inter-bots.

## COMMIT
Un seul commit :
`refactor(sugar): renommage technique complet Onizuka → Sugar Bot`
(ne pas pousser tant que le test live + déchiffrement ne sont pas validés — usage du projet).

## ÉTAPE MANUELLE (user, hors-code)
Renommer l'**application Discord** en « Sugar Bot » dans le Developer Portal pour que le nom affiché
dans le serveur change (le code ne pilote que le label interne et la bio).
