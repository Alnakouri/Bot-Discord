# PLAN — Indépendance stricte : chaque bot embarque son noyau

## Décision

**Chaque bot doit tourner sans `shared/`.** Le noyau technique est copié dans chaque
dossier bot ; `shared/` ne garde que ce qui est *réellement* partagé (état commun) ou
*réellement* optionnel (features).

Constat de départ (mesuré 2026-08-25) : **les 6 bots échouent à l'import** dès que
`shared/` est absent.

```
ECHEC bot_maiq        -> bot_maiq.py:22   from shared.response_memory import ResponseMemory
ECHEC bot_sheogorath  -> bot_sheogorath.py:23  from shared.response_memory import ResponseMemory
ECHEC bot_alfred      -> bot_alfred.py:44   from shared.response_memory import ResponseMemory
ECHEC bot_malena      -> bot_malena.py:22   from shared.smart_router import classify_request, ...
ECHEC bot_johnny      -> bot_johnny.py:20   from shared.response_memory import ResponseMemory, ...
ECHEC bot_sugar       -> bot_sugar.py:21    from shared.response_memory import ResponseMemory, ...
```

Point acquis à ne pas perdre : **aucun bot n'importe un autre bot** (vérifié, 0 sur 6).

---

## ⚠️ Le piège à comprendre avant de commencer

Le noyau **ne peut pas** être retiré de `shared/` : la pile Twitch de `shared/` en dépend.

```
shared/twitch/llm.py, dispatch.py, events.py, voice.py, daily_profile.py
shared/twitch_announcer.py, twitch_eventsub.py
shared/discord_status.py, discord_profile.py
        └── importent shared.smart_router et shared.llm_cascade
```

Donc après vendoring il y aura **7 copies** de `smart_router` : une par bot + celle de
`shared/`. Dans un même processus, le bot routera avec `core/smart_router.py` et son
côté Twitch avec `shared/smart_router.py`.

**C'est acceptable à une seule condition : les copies doivent être strictement
identiques.** Si elles le sont, savoir laquelle est chargée n'a aucune importance.
C'est le rôle de la sonde de dérive (phase 4) — elle n'est pas un bonus, c'est ce qui
rend cette architecture tenable. Sans elle, on fabrique deux routeurs divergents dans
le même processus.

---

## Périmètre : ce qui est copié, ce qui reste partagé

### À VENDORISER — le noyau, 10 modules, 1 282 lignes

Fermeture transitive calculée (aucun autre module n'est tiré) :

| module | lignes | dépend de |
|---|---|---|
| `smart_router.py` | 377 | `models` |
| `api_manager.py` | 271 | — |
| `llm_cascade.py` | 163 | `media_handler`, `safe_client`, `smart_router` |
| `media_handler.py` | 143 | `models` |
| `bot_logger.py` | 124 | — |
| `secure_env.py` | 67 | — |
| `graceful_shutdown.py` | 52 | — |
| `safe_client.py` | 50 | — |
| `response_memory.py` | 28 | — |
| `models.py` | 7 | — |

Destination : **`<Bot>/core/`** (pas en vrac dans le dossier du bot — on doit voir d'un
coup d'œil ce qui est vendorisé).

### RESTE DANS `shared/` — état partagé, import gardé + repli réel

| module | lignes | pourquoi | repli si absent |
|---|---|---|---|
| `shared_database.py` | 1163 | **État commun** entre bots (réputation, anniversaires, énigmes). Le dupliquer ne rendrait pas le bot indépendant, ça casserait sa raison d'être. | Le bot tourne sans réputation ni classement inter-bots. |
| `server_events.py` | 246 | Comportement à l'échelle du serveur (accueil, départ, anniversaires). | Pas de message d'accueil/départ. |

Ces deux-là doivent passer en `try/except ImportError` **avec un vrai repli**, pas un
no-op muet : si l'appelant ne teste pas le drapeau, on veut un comportement défini.

### NE PAS TOUCHER — déjà gardés, déjà optionnels

`memes_fr`, `games/`, `twitch/`, `twitch_chat`, `bot_features`, `discord_status`,
`discord_profile`, `slash_commands`, `healthcheck`, `ensure_writable`, `stream_listener`.
Ils sont déjà en `try/except` avec dégradation propre. Les laisser tels quels.

---

## Phase 1 — Script de vendoring

Créer **`tools/vendor_core.py`** (versionné) :

- source : `shared/<module>.py` pour les 10 modules du noyau ;
- destination : `<Bot>/core/<module>.py` pour les 6 bots ;
- réécrit les imports internes : `from shared.models import X` → `from core.models import X`,
  `from shared.smart_router import Y` → `from core.smart_router import Y` (concerne
  `llm_cascade`, `media_handler`, `smart_router`) ;
- ajoute en tête de chaque fichier copié un bandeau :

```python
# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/<module>.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.
```

- crée `<Bot>/core/__init__.py` ;
- idempotent : relancé deux fois, il ne change rien.

**`shared/` reste la source de vérité pour la maintenance.** On corrige dans `shared/`,
on relance le script, les 6 copies suivent. C'est ce qui évite le « propager 6 fois à la
main » qui a produit le bug des 31 appels bloquants.

## Phase 2 — Recâbler les 6 bots

Dans chaque `bot_*.py` **et** dans les modules locaux du bot (`sheo_llm.py`,
`*_memory.py`, `*_data.py`… — l'audit doit balayer tout le dossier) :

```python
# avant
from shared.smart_router import classify_request, RequestType, download_media, ...
from shared.response_memory import ResponseMemory, merge_recent_responses
from shared.llm_cascade import generate_response

# après
from core.smart_router import classify_request, RequestType, download_media, ...
from core.response_memory import ResponseMemory, merge_recent_responses
from core.llm_cascade import generate_response
```

Import **dur**, sans `try/except` : le module est dans le dossier du bot, il est toujours
là. Un `except ImportError` ici ne masquerait qu'une erreur d'installation.

Pour `shared_database` et `server_events`, à l'inverse :

```python
try:
    from shared.shared_database import get_or_create_user, add_reputation, log_interaction
    DB_PARTAGEE = True
except ImportError:
    DB_PARTAGEE = False
    logger.warning("[CORE] shared/ absent : reputation et classement inter-bots desactives.")
```

Et **chaque appel** doit être gardé par le drapeau. Un drapeau posé mais jamais testé est
pire que pas de drapeau : c'est le mode de panne « bot vivant mais inerte » déjà vu deux
fois (M'aiq muet sur `PermissionError`, puis sur `UnboundLocalError`).

`sys.path` : le bot tourne avec `working_dir=/app/bot`, donc `core/` est déjà importable.
Rien à ajouter au `docker-compose.yml`.

## Phase 3 — Le test qui rend la règle vérifiable

Créer **`tests/test_independance_bots.py`**.

Deux assertions, la seconde est celle qui compte :

1. **Aucun import croisé entre bots** — statique (AST), rapide. Vaut 0 aujourd'hui, doit
   le rester.
2. **Chaque bot s'importe avec `shared/` bloqué** — en **sous-processus**, un par bot :
   importer six bots dans le même interpréteur ferait collisionner leurs états globaux
   (six instances `discord.Bot`, mêmes noms de modules locaux).

Le blocage se fait par un `meta_path` finder qui lève `ImportError` sur `shared` et
`shared.*`. Prototype fonctionnel déjà validé pendant l'audit — il produit exactement la
sortie `ECHEC …` citée en tête de ce plan.

Distinguer trois issues, sinon on conclut à tort :
- `ImportError` sur `shared*` → **échec du test** (dépendance dure résiduelle) ;
- autre exception (token absent, fichier manquant) → **skip explicite** avec le motif,
  ce n'est pas le sujet ;
- import réussi → succès.

Environnement : les bots lisent leur `.env` au chargement. Le test doit fournir des
valeurs factices (`DISCORD_TOKEN`, clés API) pour ne pas dépendre des secrets réels.

## Phase 4 — Sonde de dérive (non négociable)

Créer **`tools/sonde_core_drift.py`** :

- compare `<Bot>/core/<module>.py` aux 6 bots **et** à `shared/<module>.py`, modulo la
  réécriture d'imports `shared.` → `core.` et le bandeau généré ;
- signale toute divergence, avec le bot et le module ;
- sort en **code 1** si dérive.

C'est la contrepartie du piège des 7 copies. Une divergence non détectée = deux routeurs
différents dans le même processus.

Autotest obligatoire : modifier volontairement une copie doit faire échouer la sonde. Une
sonde qui ne dit jamais « non » ne vaut rien.

## Phase 5 — CI

Créer **`.github/workflows/ci.yml`** — le dépôt n'a aucun `.github` aujourd'hui.

```yaml
- python -m pytest -q
- python tools/sonde_blocking_calls.py
- python tools/sonde_core_drift.py
```

Sans CI, les phases 3 et 4 ne tourneront que si quelqu'un y pense — et les 31 appels
bloquants ont montré que personne n'y pense.

---

## Vérification

```bash
python tools/vendor_core.py            # idempotent : 2e passage = 0 changement
python tools/sonde_core_drift.py       # attendu : 0 derive, exit 0
python tools/sonde_blocking_calls.py   # attendu : TOTAL 0, exit 0
python -m pytest -q                    # 252 tests + les nouveaux
python -m py_compile */bot_*.py */core/*.py
```

Puis, **bot par bot** (l'indépendance le permet, c'est même tout l'intérêt) :

```bash
docker compose up -d --build maiq
docker logs bot-maiq --since 5m | grep -iE "FAIL|Traceback|CORE"
```

Test live : envoyer 2-3 messages d'affilée, vérifier une réponse et l'absence de
`heartbeat blocked`. **Ne pas conclure sur « ça compile et les tests passent »** : la
régression `UnboundLocalError` du patch précédent était invisible à ces deux contrôles.

Contrôle spécifique du repli : renommer temporairement `shared/shared_database.py` et
vérifier que le bot démarre et répond, sans réputation, **sans exception**.

## Ordre recommandé

Phase 1 → 4 → 2 → 3 → 5.

La sonde de dérive (4) **avant** le recâblage (2) : dès la première copie posée, elle
garde le filet tendu. Recâbler d'abord et sonder ensuite laisse une fenêtre où la
divergence passe inaperçue.

Un seul bot en pilote (**Malena**, 757 lignes, le plus petit) sur les phases 1-2 avant
de dérouler les cinq autres.

## Ce que ce plan coûte, en clair

- **~7 700 lignes dupliquées** dans git (1 282 × 6).
- `shared/models.py` — désigné « source unique » lors de l'audit des modèles morts
  (2026-08-24) — existera en **7 exemplaires**. Chaque correction d'ID modèle devra
  repasser par `vendor_core.py`, sinon les bots divergent sur les modèles appelés.
- Toute correction de noyau = `shared/` puis `python tools/vendor_core.py` puis commit
  des 6 copies. Oublier le script = dérive silencieuse, rattrapée par la sonde
  seulement si la CI tourne.

## Ce que ce plan ne fait PAS

- Il ne duplique pas `shared_database` (état commun) ni `server_events`.
- Il ne touche pas aux imports déjà gardés (features optionnelles).
- Il ne corrige pas `max_output_tokens` absent chez Sheo/Alfred/M'aiq.
- Il n'ajoute aucun test unitaire sur le contenu de `on_message`.

---

## ÉTAT AU 2026-08-26 — phase 2 terminée, plan exécuté à 100 % (non commité)

Les 3 groupes qui restaient sont faits :

1. **Malena + Sheo passent le test d'indépendance.**
   Malena : `shared_database` + `server_events` regroupés dans un seul `try/except`
   avec drapeau `DATABASE_AVAILABLE` (idiome des 5 autres bots) + warning au démarrage ;
   **les 7 appels sont gardés** (`is_ignored_channel` ×2, `get_or_create_user`/
   `log_interaction`, `check_and_send_birthdays` + son `.start()`, `handle_member_join`,
   `handle_member_remove`).
   Sheo : `from shared.shared_database import add_reputation` supprimé des **deux**
   branches du `try/except` de chemins locaux et rapatrié dans le bloc gardé
   `DATABASE_AVAILABLE` (le seul appel, `tool_mod_reputation`, était déjà gardé).

2. **4 imports noyau en fonction** passés sur `core.` : `Sheogorath:361, 741, 742`,
   `MalenaBot:134`.

3. **14 imports qui contournaient `core/`** passés en import **dur** `from core.X` :
   `models` (Alfred, M'aiq, Sheo — les replis qui réécrivaient les IDs modèles en dur
   sont supprimés), `bot_logger` (Alfred, M'aiq, Sheo, Johnny, Sugar), `secure_env`
   (les 6). Vérifié en condition de prod (`shared/` présent) : c'est bien
   `MaiqBot/core/models.py` et `MaiqBot/core/bot_logger.py` qui sont chargés.

### Vérifications passées

| contrôle | résultat |
|---|---|
| `python -m py_compile */bot_*.py */core/*.py` | OK |
| `python tools/vendor_core.py` ×2 | idempotent, 0 changement |
| `python tools/sonde_core_drift.py` | 0 dérive, exit 0 — **autotesté** (dérive injectée → détectée + exit 1 → restaurée) |
| `python tools/sonde_blocking_calls.py` | TOTAL 0, exit 0 |
| `python -m pytest -q` | **259 passed**, 0 failed (46 subtests) — était 257/2 |
| `tests/test_independance_bots.py` | 7/7 **passed**, aucun `skip` |
| import des 6 bots **avec** `shared/` (condition de prod) | 6/6 OK |
| import Malena **sans** `shared/` | `DATABASE_AVAILABLE = False` + warning, aucune exception |

### Reste à faire

- Commit + push (rien n'est commité, dernier commit = `0131583`).
- Déploiement `docker compose up -d --build` puis **test live** : 2-3 messages d'affilée
  par bot, vérifier réponse + absence de `heartbeat blocked`.
  ⚠️ Ne pas conclure sur « ça compile et les tests passent » — la régression
  `UnboundLocalError` était invisible à ces deux contrôles.
- Contrôle du repli en conditions réelles : renommer temporairement
  `shared/shared_database.py` et vérifier qu'un bot démarre et répond sans réputation.
