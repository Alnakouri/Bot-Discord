# PLAN — Câblage Dashboard ↔ Bots Twitch (chaînes de chat + toggles + reward_map)

> **Contexte.** Le dashboard a (Phase 6) des vues Twitch v2 par bot, mais **les bots ne lisent
> jamais `data/twitch_config.json`** : les toggles (events/interjections/greetings/viewer_memory),
> le `reward_map` et — surtout — la **liste des chaînes de chat** ne pilotent rien. Aujourd'hui les
> chaînes viennent uniquement de l'env `TWITCH_CHAT_CHANNELS` (lu dans `setup_twitch_chat`,
> `shared/twitch_chat.py`). Objectif : rendre **chaînes + toggles + reward_map pilotables au
> dashboard**, sans casser l'autonomie des bots ni la sécurité.
>
> **Exigences dures** (ne pas régresser) :
> - **Secrets en env uniquement** (`TWITCH_CLIENT_ID/SECRET`, tokens). Le dashboard ne gère
>   QUE chaînes / toggles / reward_map. Jamais de secret dans `twitch_config.json`.
> - **Autonomie** ([[bots-independants]]) : si `twitch_config.json` est absent/illisible → le bot
>   fonctionne comme avant (pilotage par env). Lecture = `try/except` → `{}`.
> - **Auth + bind localhost** du dashboard préservés (`securite-audit-bots`, 31c8724).
> - **Application au redémarrage** du bot (pas de hot-reload ici — voir Hors périmètre).

---

## Prérequis / faits vérifiés (session 2026-06-24)

- `setup_twitch_chat(bot_id, logger, …)` est appelé avec `bot_id` = `"sheogorath"`, `"johnny"`, …
  → **mêmes clés que `BOT_REGISTRY`** (`dashboard/backend/bot_manager.py:6`, clés
  `sheogorath/maiq/alfred/johnny/onizuka/...`). Aucun mapping à faire.
- `twitch_config.json` vit dans `data/` : dashboard = `ROOT_DIR/"data"` (`app.py:36`,
  `TwitchConfigManager(DATA_DIR)` `app.py:134`) ; bot = `DATA_DIR = os.getenv("DATA_DIR")` ou
  `Path(__file__).parent.parent/"data"` (`twitch_chat.py:27`). **Les deux pointent au même
  `data/twitch_config.json`** en local. ⚠️ En Docker, vérifier que `DATA_DIR` (bots) et le volume
  du dashboard montent **le même dossier `data/`**, sinon le bot ne verra pas les écrits du dashboard.
- Backend existant (`dashboard/backend/twitch_config.py`) : `get_all()` initialise par bot
  `chat` (events/interjections/greetings/viewer_memory, tous `True`), `reward_map` `{}`, `listen`
  `{…}`. Méthodes `update_chat_config`, `update_reward_map`, `update_listen_config` déjà présentes.
- Endpoints existants (`app.py`) : `GET/PUT /api/twitch/chat/{bot}`, `…/rewards/{bot}`,
  `…/listen/{bot}`, `…/leaderboard/{bot}` (juste avant `@app.get("/api/twitch/leaderboard/{bot_id}")`,
  ~`app.py:408`). `Body` est déjà importé (utilisé par l'endpoint rewards).

---

## Phase A — Backend : ajouter `chat_channels` (`dashboard/backend/twitch_config.py`)

### A.1 Schéma par défaut (`get_all`, bloc d'init des clés manquantes)
Après le bloc `if "reward_map" not in config[bot_id]: …` ajouter :
```python
if "chat_channels" not in config[bot_id]:
    # Chaînes Twitch où le bot chatte. Vide => le bot retombe sur TWITCH_CHAT_CHANNELS (env).
    config[bot_id]["chat_channels"] = []
    updated = True
```

### A.2 Méthode `update_chat_channels` (à placer après `update_reward_map`)
```python
def update_chat_channels(self, bot_id: str, channels) -> list[str]:
    """Liste des chaînes où le bot chatte. Accepte liste ou CSV. Normalise chaque entrée
    via extract_login (login ou URL twitch.tv/...). Liste vide => fallback env."""
    if bot_id not in BOT_REGISTRY:
        raise ValueError(f"Bot '{bot_id}' non enregistré.")
    if isinstance(channels, str):
        channels = channels.split(",")
    if not isinstance(channels, list):
        raise ValueError("Les chaînes doivent être une liste ou une chaîne CSV.")
    cleaned = []
    for raw in channels:
        raw = str(raw).strip()
        if not raw:
            continue
        login = self.extract_login(raw)   # réutilise la validation des subscriptions
        if login not in cleaned:
            cleaned.append(login)
    config = self.get_all()
    config[bot_id]["chat_channels"] = cleaned
    self._save_raw(config)
    return cleaned
```
> `extract_login` existe déjà (`twitch_config.py:111`) : valide 3–25 alphanum/underscore et
> extrait le login d'une URL `twitch.tv/...`.

---

## Phase B — Backend : endpoints (`dashboard/backend/app.py`)

Juste **avant** `@app.get("/api/twitch/leaderboard/{bot_id}")` (~`app.py:408`), mêmes conventions
(derrière l'auth déjà appliquée aux autres `/api/twitch*`) :
```python
@app.get("/api/twitch/channels/{bot_id}")
async def get_twitch_channels(bot_id: str):
    try:
        cfg = twitch_config_manager.get_bot(bot_id)
        return {"chat_channels": cfg.get("chat_channels", [])}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/twitch/channels/{bot_id}")
async def update_twitch_channels(bot_id: str, payload: dict = Body(...)):
    try:
        cleaned = twitch_config_manager.update_chat_channels(bot_id, payload.get("chat_channels", []))
        return {"status": "ok", "chat_channels": cleaned}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

---

## Phase C — Bot : lire la config dashboard (`shared/twitch_chat.py`)

### C.1 Helper de lecture (fonction module, juste avant `def setup_twitch_chat`)
```python
def _load_dashboard_twitch_config(bot_id: str, logger) -> dict:
    """Lit data/twitch_config.json pour CE bot. Renvoie {} si absent/illisible → le bot
    reste autonome sans le dashboard (cf. [[bots-independants]])."""
    path = os.path.join(DATA_DIR, "twitch_config.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (data.get(bot_id) or {}) if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"⚠️ [TWITCH_CHAT:{bot_id}] Lecture twitch_config.json échouée (ignoré) : {e}")
        return {}
```

### C.2 Application dans `setup_twitch_chat` (gate + chaînes + toggles + reward_map)
Le gate actuel **exige** `channels_csv` (env). Le **relâcher** pour que les chaînes puissent venir
du dashboard, tout en gardant l'exigence des secrets. Remplacer le bloc actuel :
```python
if not client_id or not client_secret or not username or not channels_csv or not default_token:
    logger.info(...); return None
# … env_peers / resolved_peers …
channels = [c.strip().lower().lstrip("#") for c in channels_csv.split(",") if c.strip()]
if not channels:
    logger.info(...); return None
```
par :
```python
# Secrets => env obligatoire. channels_csv N'EST PLUS requis (dashboard peut fournir).
if not client_id or not client_secret or not username or not default_token:
    logger.info(f"📡 [TWITCH_CHAT:{bot_id}] Module chat non activé (crédentiels manquants)")
    return None

dash = _load_dashboard_twitch_config(bot_id, logger)   # {} si pas de dashboard

# resolved_peers : INCHANGÉ (garder le bloc TWITCH_PEER_BOTS existant)

# Chaînes : dashboard prioritaire si non vide, sinon env.
dash_channels = [str(c).strip().lower().lstrip("#") for c in dash.get("chat_channels", []) if str(c).strip()]
env_channels  = [c.strip().lower().lstrip("#") for c in (channels_csv or "").split(",") if c.strip()]
channels = dash_channels or env_channels
if not channels:
    logger.info(f"📡 [TWITCH_CHAT:{bot_id}] Aucune chaîne (ni dashboard ni TWITCH_CHAT_CHANNELS)")
    return None
if dash_channels:
    logger.info(f"📡 [TWITCH_CHAT:{bot_id}] Chaînes pilotées par le dashboard : {channels}")

# Toggles : le dashboard prime SUR LES ARGS quand la clé est présente.
dash_chat = dash.get("chat") or {}
if "events" in dash_chat:        enable_events         = bool(dash_chat["events"])
if "interjections" in dash_chat: enable_interjections  = bool(dash_chat["interjections"])
if "greetings" in dash_chat:     enable_greetings      = bool(dash_chat["greetings"])
if "viewer_memory" in dash_chat: enable_viewer_memory  = bool(dash_chat["viewer_memory"])

# reward_map : merge dashboard PAR-DESSUS les défauts du bot (un dashboard vide ne les efface pas).
dash_rewards = dash.get("reward_map") or {}
if dash_rewards:
    eventsub_reward_map = {**(eventsub_reward_map or {}), **dash_rewards}
```
> ⚠️ Conserver intacts dans ce bloc : la résolution `env_peers/resolved_peers` (fix anti-bots) et,
> plus bas, la construction `broadcaster_auth` + l'instanciation `TwitchChatBot(...)` (fixes déjà
> en place, NE PAS toucher).

### Vérif Phase C
- `py_compile`. Bot démarrable **sans** `twitch_config.json` (log « non activé » seulement si
  secrets manquants ; sinon fallback env). Avec un `twitch_config.json` qui fixe `chat_channels`
  → le bot JOIN ces chaînes (log « pilotées par le dashboard »). Toggle `greetings=false` au
  dashboard → plus d'accueil après redémarrage.

---

## Phase D — Frontend : champ « Chaînes de chat » (`dashboard/frontend/`)

### D.1 `index.html` — vue « Présence & connexion »
Ajouter, dans la section Twitch « Présence & connexion » (par bot, via `BOT_REGISTRY`), un champ
texte **Chaînes de chat** (CSV ou une par ligne) + bouton **Enregistrer**. Réutiliser le style des
autres cartes Twitch (cf. les blocs toggles/rewards déjà présents).

### D.2 `js/app.js`
- `GET /api/twitch/channels/{bot}` au chargement de la vue → pré-remplir le champ
  (`chat_channels.join(", ")`).
- Au submit : `PUT /api/twitch/channels/{bot}` avec `{ "chat_channels": [...] }` (split sur `,`
  et/ou retour-ligne, trim). Afficher le retour `cleaned` (logins normalisés) + un toast.
- Indiquer à l'UI que **les changements s'appliquent au redémarrage du bot** (les toggles/rewards
  aussi — ce n'est pas du hot-reload).

### Vérif Phase D
Champ visible par bot, valeurs persistées dans `twitch_config.json`, login invalide → message
d'erreur backend remonté proprement. Vues existantes intactes, auth/bind localhost préservés.

---

## Vérifications transverses (avant test live)
- `python -m py_compile` sur `shared/twitch_chat.py`, `dashboard/backend/twitch_config.py`,
  `dashboard/backend/app.py`.
- **Autonomie** : renommer temporairement `data/twitch_config.json` → le bot démarre pareil (env).
- **DATA_DIR** : confirmer que bot et dashboard lisent/écrivent le MÊME `data/twitch_config.json`
  (surtout en Docker : volume commun).
- **Sécurité** : aucun secret ajouté à `twitch_config.json` ; endpoints derrière l'auth ;
  bind localhost inchangé.
- **Gotcha** : relancer `start_dashboard.bat` après modif backend (`plan-dashboard-hybride-bots`),
  et **redémarrer les bots** pour qu'ils relisent la config.

## Hors périmètre (pour plus tard)
- **Hot-reload** (re-JOIN des chaînes / re-toggle sans redémarrage du bot) : nécessiterait un
  watcher de fichier + commandes IRC JOIN/PART à chaud côté `TwitchChatBot`. Noté, pas maintenant.
- Édition du `listen` (Phase 5 STT) déjà couverte par l'UI existante ; non concernée ici.

## Rollback
Tout est additif + dégradation propre : supprimer/renommer `twitch_config.json` ou laisser
`chat_channels` vide rétablit le comportement « env uniquement ». Aucune migration de données.
