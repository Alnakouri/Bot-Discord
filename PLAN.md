# PLAN — Twitch : « silence sauf si nommé » + Sugar sur le chat Twitch

## Contexte & décisions (validées avec l'utilisateur)
1. **Écoute active (voix/STT)** : DÉJÀ conforme — `shared/twitch/voice.py:47`
   (`if not self.trigger_re.search(text): return`). Un bot ne réagit au micro que si
   son nom/surnom/nom complet est prononcé. **NE RIEN CHANGER ICI.**
2. **Chat texte** : les bots s'incrustent via **interjections spontanées**
   (`shared/twitch/dispatch.py:164`) et **accueils** de viewers (`:161`). Décision user :
   **silence sauf si nommé** → couper interjections + accueils sur Twitch. On GARDE :
   réponse quand nommé (`trigger_re`), commandes `!cmd`, et événements (sub/raid/bits).
3. **Sugar sur Twitch** : la brancher sur le chat (elle a déjà l'ANNONCEUR de lives,
   `setup_twitch_announcer` l.431-439 de `bot_sugar.py`, mais PAS la présence chat).
   Persona = **identique à Discord** (`PERSONALITY_PROMPT`). Conformité ToS héritée
   automatiquement (tout passe par `send_chat_safe` + `ANTI_INJECTION_GUARD`).
4. Workflow : **Antigravity exécute ce plan.** Claude a rédigé.

## Rappel architecture
- Le **dashboard fait autorité** : `data/twitch_config.json` écrase les args de code
  (`shared/twitch_chat.py:325-334`). Donc tout toggle doit être posé AUX DEUX endroits :
  args de `setup_twitch_chat(...)` ET `twitch_config.json` (sinon le JSON ré-active).
- Bots avec chat Twitch AUJOURD'HUI : **Sheo** et **Johnny** uniquement. Sugar = 3e.
- Anti-boucle inter-bots sur Twitch : chaque bot ignore les pseudos des autres via
  `TWITCH_PEER_BOTS` (env) + arg `peer_bots`. Logins chat connus :
  `compte_bot_sheo` (Sheo), `johnny_alt_silverhand` (Johnny).

---

## PARTIE A — Silence spontané sur Twitch (interjections + accueils OFF)

### A.1 — `data/twitch_config.json` (source de vérité, prioritaire)
Pour **chaque** bloc bot (`sheogorath`, `maiq`, `alfred`, `johnny`, `sugar`, `malena`,
`onizuka`), dans `"chat"`, passer :
```json
"interjections": false,
"greetings": false,
```
(laisser `"events": true`, `"viewer_memory": true`, `"game_qa": false` inchangés).

### A.2 — Args de code (défaut cohérent, au cas où le JSON serait absent)
- **Sheo** `Sheogorath/bot_sheogorath.py:820-823` : `enable_interjections=True` → `False`,
  `enable_greetings=True` → `False`.
- **Johnny** `JohnnyBot/bot_johnny.py:512+` (bloc `setup_twitch_chat`) : idem, mettre
  `enable_interjections=False`, `enable_greetings=False`.

### A.3 — Ce qu'on NE touche PAS
- `enable_events` reste `True` (réactions sub/raid/bits = événements, pas de l'incrustation).
- Réponse quand nommé (`trigger_re`) et commandes `!cmd` : inchangées.
- `passive_handler` de Sheo (faveur passive) et `game_qa`/`cohost_channels` sont déjà
  soit spécifiques soit OFF (`game_qa:false`, `cohost_channels:[]`) → rien à faire.
  (Si un jour on veut ZÉRO sortie passive, revoir `passive_handler` — hors périmètre ici.)

---

## PARTIE B — Sugar sur le chat Twitch (câblage code, en miroir de Sheo)

Tout le code va dans **`SugarBot/bot_sugar.py`**. Modèle de référence :
`Sheogorath/bot_sheogorath.py` (imports 167-174, globals 173-174, setup 812-838, stop 2537-2544).

### B.1 — Imports (près de l'import `setup_twitch_announcer` existant)
Mettre le pattern try/except (autonomie, cf. bots indépendants) :
```python
try:
    from shared.twitch_chat import setup_twitch_chat
    TWITCH_CHAT_AVAILABLE = True
except ImportError:
    TWITCH_CHAT_AVAILABLE = False
    def setup_twitch_chat(*a, **k): return None
```

### B.2 — Globals module (près des autres globals Twitch)
```python
twitch_chat = None
twitch_chat_task = None
```

### B.3 — Dans `on_ready` (`bot_sugar.py`), APRÈS le bloc `twitch_announcer` (après l.439)
Idempotent (on_ready peut refire au RESUME → garde `twitch_chat is None`) :
```python
    global twitch_chat, twitch_chat_task
    if TWITCH_CHAT_AVAILABLE and twitch_chat is None:
        twitch_chat = setup_twitch_chat(
            "sugar", logger,
            personality_prompt=PERSONALITY_PROMPT, key_manager=key_manager,
            mistral_client=mistral_client, groq_client=groq_client,
            openrouter_client=openrouter_client, bot_label="Sugar Bot",
            enable_events=True,
            enable_interjections=False,   # décision « silence sauf si nommé »
            enable_greetings=False,       # idem
            enable_viewer_memory=True,
            enable_eventsub=False,        # pas de token broadcaster Sugar → évite les 403 ; réactiver plus tard si besoin
            enable_voice_listen=False,
        )
        if twitch_chat:
            twitch_chat_task = asyncio.create_task(twitch_chat.run())
```
- **Persona identique Discord** : on passe `PERSONALITY_PROMPT` (celui de `sugar_data.py`).
  Les augmentations par-message (carnet de rancunes, mémoire, ton) sont Discord-only —
  normal, ce sont des systèmes Discord. La VOIX/le CARACTÈRE sont identiques.
- Pas de `commands=` au début (Sugar n'a pas de commandes Twitch dédiées) → l'infra
  tourne sans. On pourra en ajouter plus tard.

### B.4 — Arrêt propre (miroir `bot_sheogorath.py:2537-2544`)
Dans le chemin de shutdown de Sugar (là où `setup_graceful_shutdown(bot)` / `on_disconnect`
ferme les ressources) :
```python
    global twitch_chat, twitch_chat_task
    if twitch_chat:
        twitch_chat.stop()
    if twitch_chat_task:
        twitch_chat_task.cancel()
        try:
            await twitch_chat_task
        except asyncio.CancelledError:
            pass
```

### B.5 — Anti-boucle : peer bots (config, PAS de code)
- Ajouter le **login chat de Sugar** (ex. `sugar_bot_xxx`, cf. B.6) aux `TWITCH_PEER_BOTS`
  de **Sheo** et **Johnny** (`.env.encrypted` de chaque bot).
- Ajouter `compte_bot_sheo` ET `johnny_alt_silverhand` aux `TWITCH_PEER_BOTS` de **Sugar**.

---

## À FAIRE PAR L'UTILISATEUR (externe — Antigravity ne peut pas)
Sans ces credentials, `setup_twitch_chat` renvoie `None` proprement (bot Discord intact).
1. **Créer un compte Twitch** pour Sugar (identité de chatteuse, ex. `sugar_bot_xxx`).
2. **Créer une application Twitch** (dev.twitch.tv/console) → `client_id` + `client_secret`
   (1 appli par bot, cf. règle projet).
3. Renseigner dans **`SugarBot/.env`** (sera re-chiffré) :
   `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TWITCH_BOT_USERNAME=<login sugar>`.
4. **Autoriser** : `python twitch_authorize.py --bot sugar` avec le compte de Sugar →
   génère `TWITCH_OAUTH_TOKEN` + `TWITCH_REFRESH_TOKEN` (comme fait pour Sheo/Johnny).
5. **`data/twitch_config.json`** bloc `"sugar"` : mettre
   `"chat_channels": ["chaine_du_dev"]` (actuellement `[]`) + les toggles A.1.

---

## VÉRIFICATIONS ATTENDUES
- `python -m py_compile SugarBot/bot_sugar.py Sheogorath/bot_sheogorath.py JohnnyBot/bot_johnny.py`.
- `python -m pytest tests/test_twitch_features.py` reste vert.
- Chaque bot reste importable seul (0 dépendance runtime inter-bot).
- JSON valide : `python -c "import json;json.load(open('data/twitch_config.json'))"`.
- Test live (après credentials user) :
  - Sugar rejoint `#chaine_du_dev`, log `🎯 Déclencheurs configurés : [...'sugar'...]`.
  - Chat « ce jeu est dur » → **aucun** bot ne répond (silence spontané OK).
  - Chat « sugar t'es nulle » → Sugar répond, en personnage Discord, sortie filtrée ToS.
  - Voix « sugar ... » → Sugar réagit ; voix sans nom → silence (déjà en place).
  - Aucune boucle Sugar↔Sheo↔Johnny (peer bots OK).
