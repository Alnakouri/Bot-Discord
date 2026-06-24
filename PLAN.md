# PLAN — Bots Twitch v2 (détaillé) : indépendance, mémoire, économie, channel points, écoute live + dashboard 2 sections

> **Contexte** : `shared/twitch_chat.py` fait déjà vivre Sheo sur Twitch (mention, events
> USERNOTICE/bits, interjections, commandes, accueil, anti-répétition + contexte — commité
> d2cd975). On élargit dans 5 directions + le dashboard, **tout en gardant le module
> générique** (Sheo = pilote, les autres bots héritent), avec deux exigences dures :
>
> - **Indépendance/cloisonnement** (`bots-independants`, `securite-audit-bots`) : Sheo et
>   Johnny ont les **mêmes features** mais **aucune donnée partagée** entre eux ni avec
>   Discord. Toute persistance est suffixée `*_{bot_id}.json`. Johnny **n'importe jamais** un
>   module de `Sheogorath/` (dépendance inter-bot interdite) ; il passe par `shared/` (optionnel,
>   try/except ImportError → no-op) ou ses propres fichiers.
> - **Anti-saturation** : tout message **spontané** (events, interjections, accueil, channel
>   point, réponse-voix) passe par le plafond global `global_msg_timestamps` (18/30 s) **avant
>   envoi** + cooldown propre. Commandes ≈ 0 LLM.

---

## Prérequis communs (à faire AVANT les phases concernées)

### P.1 — Secrets Twitch par bot (Phase 1+)
Chaque bot a sa **propre app Twitch** (1 app/bot, `projet-bots-sur-twitch`). Les variables sont
lues par `setup_twitch_chat` (`twitch_chat.py:1327-1332`) **dans l'environnement du process du
bot** → donc même noms de variables, **valeurs différentes par bot** (chaque `.env`/secret bot) :
`TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TWITCH_BOT_USERNAME`, `TWITCH_CHAT_CHANNELS`,
`TWITCH_OAUTH_TOKEN`, `TWITCH_REFRESH_TOKEN`, `TWITCH_PROFILE_BIO` (opt), `TWITCH_CHAT_COLOR` (opt).
→ **Aucun code à changer pour l'isolation** : c'est de la config par bot. Johnny obtient les
siennes via son secret chiffré (`plan-chiffrement-par-bot`). **Ne jamais réutiliser le token de Sheo.**

### P.2 — Scopes Twitch (Phase 4 — EventSub)
Re-auth **par bot** (comme l'historique chat) pour ajouter les scopes nécessaires :
`channel:read:redemptions` (channel points), `moderator:read:followers` (follows),
`bits:read`, `channel:read:subscriptions`, `channel:read:hype_train`, `channel:read:polls`.
Garder le flux d'auth existant (`TwitchAuth`), juste élargir la liste de scopes demandée.

### P.3 — Dépendances Python (par phase)
- Phase 2/3/4 : rien de neuf (stdlib + `aiohttp` déjà présent).
- Phase 5 : `sounddevice` (capture micro Windows), `grpcio`/`grpcio-tools` (client NIM A) **ou**
  `nemo_toolkit[asr]` (chemin B, sous WSL2), `webrtcvad` optionnel. Côté service : **Docker
  Desktop + WSL2 + NVIDIA Container Toolkit + `NGC_API_KEY`** (chemin A) ou env CUDA WSL2 (B).
- Lister ces deps dans `requirements.txt` **derrière commentaire « STT optionnel »** pour ne
  pas casser l'install des bots qui n'utilisent pas l'écoute live.

---

## Phase 1 — Porter Johnny sur Twitch (parité Sheo) — `JohnnyBot/bot_johnny.py`

Johnny hérite **gratuitement** des features génériques du module. Travail = **câblage** dans son
`on_ready` (`bot_johnny.py:240`) + **adaptateurs propres** (calqués sur `bot_sheogorath.py:554-700`).

### 1.1 Imports défensifs (haut de `bot_johnny.py`)
```python
try:
    from shared.twitch_chat import setup_twitch_chat
    TWITCH_CHAT_AVAILABLE = True
except ImportError:
    TWITCH_CHAT_AVAILABLE = False
    def setup_twitch_chat(*a, **k): return None
twitch_chat = None
twitch_chat_task = None
```

### 1.2 Bloc de setup dans `on_ready`
- Reprendre le squelette `if TWITCH_CHAT_AVAILABLE and twitch_chat is None:` de Sheo.
- `bot_id="johnny"`, `bot_label="Johnny Silverhand"`, `personality_prompt=johnny_data.<PROMPT_BASE>`,
  `system_prompt_provider=lambda: <prompt vivant Johnny>` (équivalent de `current_system_prompt`).
- Passer `key_manager`/clients LLM de Johnny (ses propres clés).
- Activer : `enable_events=True, enable_interjections=True, interjection_chance=0.03,
  interjection_min_interval=600.0, enable_greetings=True, enable_viewer_memory=True` (Phase 2),
  `commands=…, command_aliases=…, passive_handler=…` (1.3), `enable_eventsub=True, reward_map=…`
  (Phase 4).
- `twitch_chat_task = asyncio.create_task(twitch_chat.run())`.

### 1.3 Adaptateurs de commandes Johnny (équivalents, **pas** copies de Sheo)
Mêmes signatures `(author: str, args: str) -> str | Awaitable[str]` :
- `cmd_johnny` / `cmd_chrome` (statiques, listes de punchlines Silverhand, 0 LLM, préfixe 🎸/🤘).
- `cmd_punchline(author, args)` **async** → générateur texte court (≈ `cmd_decret` de Sheo mais
  sans rôle/image) : prompt « balance une punchline cyberpunk cynique à @{author} », cascade
  `RequestType.TEXT`, `max_tokens=80`, repli sur une liste statique. Réutilise
  `TwitchChatBot._strip_stage_directions`.
- `cmd_cred` / `cmd_classement` → éco Johnny (Phase 3).
- `commands = {"johnny":…, "chrome":…, "punchline":…, "cred":…, "classement":…}`,
  `command_aliases = {"punch":"punchline", "leaderboard":"classement", "rep":"cred"}`.

### 1.4 Profil autonome quotidien
- Réutiliser le mécanisme générique `twitch_profile_{bot_id}.json` (déjà dans le module).
  Définir `johnny_data.TWITCH_BIO` (bio de départ) ; la persona pioche bio+couleur 1×/jour.

### Vérif Phase 1
`py_compile` ; Johnny **importable seul** ; démarre **sans** secrets Twitch (no-op propre,
log « non activé ») ; avec secrets → répond sur « johnny », `!johnny`/`!punchline` OK ;
**grep** : aucune lecture de fichier `sheo_*` ni import `Sheogorath.*` dans Johnny.

---

## Phase 2 — Mémoire long terme des habitués (générique, cloisonnée) — `shared/twitch_chat.py`

Parité Discord (`fact_brain`, `bot_sheogorath.py:1908-1934`) mais **par bot** et **séparée de Discord**.

### 2.1 Nouveaux params
`setup_twitch_chat` + `TwitchChatBot.__init__` : `enable_viewer_memory: bool = False`,
`viewer_memory_max: int = 8`. Propager comme les autres flags (`:287-294`, `:1316-1322`, `:1373-1380`).

### 2.2 Stockage — `data/twitch_facts_{bot_id}.json`
Schéma : `{ "<login_lower>": ["aime le métal", "déteste le fromage", …] }` (cap `viewer_memory_max`,
FIFO). Méthodes (calquées sur `_load/_save_viewers_state`) :
- `self.viewer_facts = self._load_viewer_facts()` dans `__init__` (si `enable_viewer_memory`).
- `_load_viewer_facts()`, `_save_viewer_facts_debounced()` (debounce 30 s comme viewers_state).

### 2.3 Injection + extraction dans `_generate_response`
- **Injection** (avant l'appel LLM) : si faits pour `author`, ajouter au `system_prompt` un bloc
  `\n[CE QUE TU SAIS SUR {author}]:\n- …\nUtilise ces infos pour personnaliser ta réponse.`
- **Instruction d'extraction** (comme `:1934`) : ajouter au prompt l'ordre de finir par
  `<fact>…</fact>` si un fait nouveau apparaît.
- **Parsing** (après réception, AVANT envoi) : `facts = re.findall(r"<fact>(.*?)</fact>", text, re.S)` ;
  retirer les blocs du texte (`re.sub`) ; pour chaque fait : `clean,_ = self._sanitize_input(fact)`,
  cap longueur (~120), append (FIFO) dans `viewer_facts[author_lower]`, `_save_viewer_facts_debounced()`.
- **Sécurité** : un fait n'est **jamais** exécuté, juste réinjecté ; passe par `_sanitize_input`.

### Vérif Phase 2
Fait appris chez Sheo **absent** chez Johnny et sur Discord (fichiers distincts) ; persiste après
redémarrage ; cap respecté ; bloc `<fact>` **jamais** visible dans le chat Twitch.

---

## Phase 3 — Économie / leaderboard, **distincte par bot** — `shared/twitch_economy.py` (nouveau) + adaptateurs

### 3.1 Moteur générique `shared/twitch_economy.py` (nouveau)
Extraire la logique de `Sheogorath/sheo_faveur.py` en **moteur paramétrable** (sans toucher
au fichier de Sheo, qui marche) :
```python
class PointsEconomy:
    def __init__(self, filename, ranks: list[dict], gain_min=1, gain_max=3): ...
    def get_points(self, login) -> int
    def add_points(self, login, points) -> tuple[int, dict|None, dict|None, bool]  # total, old_rank, new_rank, rank_up
    def get_rank(self, login) -> dict           # {name, emoji, threshold}
    def check_message(self, text) -> int        # points gagnés pour un message (longueur/mots-clés)
    def leaderboard(self, n=10) -> list[tuple[str,int]]   # top logins triés
```
Persistance atomique (write tmp + `os.replace`, comme `twitch_config.py:25-39`). Fichier **par bot**.

### 3.2 Sheo — Faveur du Prince (Twitch) — *léger ajout, pas de refonte*
- Garder `sheo_faveurs_twitch.json` + `FaveurSystem`. **Ajouter** `cmd_classement` :
  lire le top 10 (ajouter une petite méthode `leaderboard(n)` à `FaveurSystem` si absente) et
  le formater en personnage (« Voici les courtisans qui ont le plus amusé le Prince… »).
- `commands["classement"] = cmd_classement` + alias `"leaderboard":"classement"`.

### 3.3 Johnny — « Street cred » (Twitch), **nouveau et cloisonné**
- **Interdit** : `shared.shared_database.add_reputation` (= réputation Discord). 
- `from shared.twitch_economy import PointsEconomy` (shared autorisé, fallback no-op si absent).
- `johnny_cred = PointsEconomy("data/johnny_cred_twitch.json", ranks=JOHNNY_TWITCH_RANKS)`.
- `JOHNNY_TWITCH_RANKS` (dans `johnny_data.py`) au ton Night City, ex. :
  `Nobody → Choom → Edgerunner → Solo → Légende de Night City`.
- `cmd_cred(author,_)` → rang+points ; `cmd_classement(author,_)` → top 10 ; `passive_handler`
  qui crédite les messages (anti-farm : cooldown/plafond comme la faveur).

### 3.4 Garde-fous d'indépendance
Aucun import croisé, aucun fichier commun. `grep` final : `johnny_cred_twitch.json` ≠
`sheo_faveurs_twitch.json` ≠ réputation Discord.

### Vérif Phase 3
Points Johnny ≠ Sheo ≠ Discord ; `!classement`/`!cred` corrects ; `PointsEconomy` testé sur un
jeu de données (add → rank_up au franchissement de seuil, leaderboard trié).

---

## Phase 4 — Channel points & événements riches (EventSub) — `shared/twitch_eventsub.py` (nouveau)

Aujourd'hui events = IRC `USERNOTICE`/bits. EventSub (WebSocket) ouvre le reste **sans polling**.

### 4.1 Module `shared/twitch_eventsub.py`
```python
class TwitchEventSub:
    def __init__(self, bot_id, logger, auth: TwitchAuth, client_id,
                 broadcaster_id, emit, subscriptions: list[str], reward_map: dict|None=None): ...
    async def run(self): ...   # connexion + reconnexion/backoff (comme TwitchChatBot.run)
```
- WS `wss://eventsub.wss.twitch.tv/ws` → message `session_welcome` donne `session.id`.
- Pour chaque type dans `subscriptions`, **POST Helix** `/eventsub/subscriptions` avec
  `transport={method:"websocket", session_id}` + le token broadcaster (scopes P.2).
- `keepalive`/`reconnect` gérés selon les messages EventSub ; backoff sur coupure.
- `emit` = **callback fourni par le `TwitchChatBot`** : `async emit(text) -> bool` qui applique
  le **plafond global** `global_msg_timestamps` puis envoie sur le WS chat. Ainsi events + chat
  partagent **le même budget** (jamais de saturation).

### 4.2 Types d'abonnement (off par défaut, configurables)
- `channel.channel_points_custom_reward_redemption.add` → `reward_map[title]` :
  - mappe sur une **commande** (ex. « Décret » → `cmd_decret`, « Punchline » → `cmd_punchline`),
  - ou une **réaction LLM courte** en personnage si non mappé.
- `channel.follow`, `channel.raid`, `channel.hype_train.begin/progress/end`,
  `channel.poll.begin/end` → réactions courtes (repli scripté si LLM indispo).

### 4.3 Garde-fous
- 1 réaction par event ; cooldown **par type** ; anti-rafale (hype train : begin + end max).
- Tout passe par `emit` → budget global commun. Si plafond atteint → log + **drop** (pas de file).
- `reward_map` éditable au **dashboard** (Phase 6.2).

### 4.4 Intégration & activation
- `TwitchChatBot` reçoit `enable_eventsub: bool=False`, `subscriptions: list`, `reward_map: dict`,
  instancie `TwitchEventSub` après connexion chat (il connaît le `broadcaster_id` via Helix
  `Get Users`), et lance sa task. Expose `emit`.
- Sheo & Johnny → `enable_eventsub=True` + leur `reward_map` propre.

### Vérif Phase 4
Scope manquant → **log clair + dégradation propre** (pas de crash) ; redemption simulée → 1
réaction / mappée sur la bonne commande ; rafale (raid + redemptions) ≤ budget global.

---

## Phase 5 — Écoute du streamer (STT continu + jugement) — `shared/stream_listener.py` (nouveau) — **EXPÉRIMENTAL**

> Décision : **écoute continue + jugement**, sur **Sheo ET Johnny**, **un seul flux micro**.
> Partie la plus lourde → **dernière**, derrière flag, sans bloquer 1-4.

### 5.1 Moteur STT — **NVIDIA Nemotron 3.5 ASR, local & gratuit** (RTX 4060 Ti)
> Le hub tourne sur le PC de stream (RTX 4060 Ti + i7-9800X 16t + 32 Go) → STT **100 % local,
> 0 coût API, audio qui ne quitte jamais la machine**. (La contrainte « sans GPU » de
> `feature-gpu-parkee-oracle` ne visait que le déploiement Oracle, pas ce PC.)

**Modèle : `nvidia/nemotron-3.5-asr-streaming-0.6b`** — Cache-Aware FastConformer-RNNT, 600M,
**40 locales dont le FR**, **streaming natif < 100 ms**, licence **OpenMDW-1.1** (commercial OK),
GPU **Lovelace = 4060 Ti supporté**, **léger** (laisse la VRAM au jeu/encodage). Traite chaque
frame **une seule fois** ; **endpointing intégré** (finalise les segments sur les pauses) → ~pas
besoin de VAD externe (juste une garde d'énergie anti-silence).

**Deux chemins de mise en route — à trancher au tout début de Phase 5 :**
- **(A) NIM Docker — visé.** `nvcr.io/nim/nvidia/nemotron-asr-streaming:latest`, endpoint **gRPC
  `localhost:50051`** (+ HTTP 9000). Docker Desktop + **WSL2** + NVIDIA Container Toolkit +
  `NGC_API_KEY`. Le hub Windows = **client gRPC**. ⚠️ Vérifier que le **NIM streaming est GA**
  (annoncé, peut-être pas publié au 06/2026) ; sinon → (B).
- **(B) NeMo Python.** `nemo_asr.models.ASRModel.from_pretrained("nvidia/nemotron-3.5-asr-streaming-0.6b")`
  + script officiel **cache-aware streaming** (`examples/asr/asr_cache_aware_streaming/...`,
  `conformer_stream_step()`). NeMo s'installe le plus proprement **sous WSL2 Ubuntu**.
- **(C) Repli low-friction : faster-whisper** (`large-v3-turbo`, `pip install`, trivial Windows,
  ~1-2 s/énoncé) si A et B bloquent. Même flag, même hub.

**Gotcha micro ↔ WSL2/Docker :** WSL2/Docker n'exposent **pas** simplement le micro Windows. →
**Capturer l'audio côté Windows natif** (`sounddevice`) et **streamer les frames PCM vers le
service ASR** (gRPC 50051 en A ; IPC/localhost en B). Découple capture (Windows) ↔ inférence (GPU/WSL2).

### 5.2 Hub `shared/stream_listener.py`
- **Hub Windows** qui possède le micro **une seule fois**. Pipeline : capture PCM Windows →
  garde d'énergie anti-silence → frames vers service ASR → **énoncés finalisés** (endpointing) →
  publication aux bots.
- Publication, 2 modes : **même process** (callback) ou **multi-bot** (petit **WebSocket
  localhost**, chaque bot s'abonne). `listen_owner` ouvre le micro ; les autres sont abonnés.
- **Service ASR partagé** par les 2 bots (un seul modèle chargé) → empreinte GPU/mémoire **unique**.

### 5.3 Jugement par bot + arbitrage (anti-double-réponse)
- Chaque bot reçoit l'énoncé et décide **indépendamment** : gate proba + intervalle min (comme
  les interjections) **+** pertinence persona (nom du bot prononcé → priorité forte ; sinon
  classify léger « le sujet parle au bot ? »).
- **Arbitrage hub** : jeton « claim » par énoncé → **au plus un** bot répond (priorité au bot
  nommé, sinon round-robin/aléatoire). Jamais Sheo **et** Johnny sur le même énoncé.
- La réponse passe par le **plafond global** du bot choisi (anti-saturation).

### 5.4 Garde-fous STT (saturation = risque élevé ici)
- Intervalle min **global** d'écoute (≥ 45 s entre 2 réponses-voix, tous bots confondus).
- Longueur d'énoncé min (ignore « euh », toux, mots isolés).
- **Kill-switch** dashboard + compteur de transcriptions + log. **Off par défaut**
  (`enable_voice_listen=False`).
- Choix **chunk** (80/160/560/1120 ms) + device (GPU/CPU) + bascule **(C) faster-whisper CPU**
  si le GPU sature en jeu lourd → exposés au dashboard (§6.2).

### 5.5 Activation & déploiement
- Params : `enable_voice_listen=False`, `listen_owner: str`, `voice_min_interval=45`,
  `voice_chance`, `asr_endpoint`/`asr_mode`.
- Le hub tourne **là où est le micro** (PC de stream). Si les bots migrent serveur plus tard,
  le hub reste local et relaie via WebSocket (noté pour `plan-deploy-oracle`).

### Vérif Phase 5
Parler → **1 seule** réponse (jamais les 2 bots) ; silence → **0** appel STT ; intervalle min
tenu ; kill-switch coupe net ; bots **toujours fonctionnels** si STT off/HS ; bascule CPU OK.

---

## Phase 6 — Dashboard : 2 sections Discord / Twitch — `dashboard/`

### 6.1 Navigation (`frontend/index.html:46-54`)
Remplacer la `ul.nav-links` plate par **2 groupes** (titres de section non cliquables) :
```
▸ DISCORD : Vue d'ensemble · Logs · Analyse Erreurs · Clés API · Conversations · Rapports
▸ TWITCH  : Présence & connexion · Événements / Channel points · Habitués & éco · Écoute live · Annonces
```
- Garder le routage `data-target` existant (`app.js`) ; l'actuelle `#twitch` (annonces) devient
  l'item **« Annonces »**. Ajouter 4 nouvelles `<section class="view">`.

### 6.2 Nouvelles vues Twitch (par bot, via `BOT_REGISTRY`)
- **Présence & connexion** : statut connecté/déconnecté, chaîne, profil du jour (bio+couleur),
  toggles `enable_events/interjections/greetings/viewer_memory`.
- **Événements / Channel points** : table **reward → action** (`reward_map`), toggles d'abonnements.
- **Habitués & éco** : leaderboards (faveur Sheo / cred Johnny), nb de viewers connus.
- **Écoute live** : on/off (**kill-switch**), device micro, **chemin ASR (A/B/C) + device GPU/CPU
  + chunk**, intervalle min, compteur de transcriptions.

### 6.3 Backend (`dashboard/backend/`)
- Étendre `twitch_config.py` : le schéma par bot (`get_all`, `:49-53`) gagne des clés
  `chat: {events, interjections, greetings, viewer_memory}`, `reward_map: {}`,
  `listen: {enabled, mode, device, chunk_ms, min_interval}`. Écriture atomique déjà en place.
- Nouveaux endpoints `app.py` (mêmes conventions que `/api/twitch*`, `:296-303`, **derrière
  l'auth** `:154-158`) : `GET/PUT /api/twitch/chat/{bot}`, `GET/PUT /api/twitch/rewards/{bot}`,
  `GET/PUT /api/twitch/listen/{bot}`, `GET /api/twitch/leaderboard/{bot}`.
- **Ne pas régresser** : bind localhost + auth mot de passe (`securite-audit-bots`, 31c8724).
- **Gotcha** : relancer `start_dashboard.bat` après modif backend (`plan-dashboard-hybride-bots`).

### Vérif Phase 6
Les 2 groupes s'affichent, vues existantes **intactes**, réglages **persistés par bot**,
auth/bind localhost préservés, kill-switch écoute fonctionnel.

---

## Séquencement & dépendances
1. **Phase 1** (Johnny sur Twitch) — débloque la parité, faible risque.
2. **Phase 2** (mémoire habitués) + **Phase 3** (éco par bot) — génériques, faible risque.
3. **Phase 6** (dashboard 2 sections) — dès que 1-3 exposent des réglages.
4. **Phase 4** (EventSub/channel points) — nécessite re-auth scopes par bot (P.2).
5. **Phase 5** (écoute live STT) — en dernier, expérimental, derrière flag.

## Vérifications transverses (avant chaque test live)
- `python -m py_compile` sur **tous** les fichiers touchés.
- **Checklist cloisonnement** (grep) : aucun chemin de données partagé Sheo↔Johnny↔Discord ;
  Johnny n'importe **aucun** module `Sheogorath/*` ; fichiers `*_{bot_id}.json` distincts.
- Chaque bot **importable et démarrable seul** (secrets/STT absents → no-op propre).
- **Anti-saturation** : flot massif (events + redemptions + voix + mentions) ≤ 18 envois/30 s
  **par bot** (logs `🚨 rate limit`) ; jamais 2 bots sur le même énoncé voix.
- Toutes les nouvelles features **off par défaut** ; replis si LLM/STT/clé indisponibles.

## Rollback
Chaque phase = commit séparé. Les flags `enable_*=False` par défaut permettent de **désactiver
sans rollback de code**. Phase 5 isolée dans `shared/stream_listener.py` → suppressible sans
impacter le chat.

## Hors périmètre (pour l'instant)
- Généralisation aux 4 autres bots (M'aiq, Onizuka, Alfred, Malena) — module prêt, plus tard.
- Modération/timeout Twitch (exclu par design).
- Voix clonée / vision GPU restent parkées pour le **déploiement** (`feature-gpu-parkee-oracle`) ;
  le STT tourne **en local** sur le PC de stream — pas concerné.
- Annonces de live Discord : déjà couvertes par l'item « Annonces » (code `plan-twitch-announce`).
