# PLAN — Phase 5 : Écoute live du streamer (STT continu + jugement) sur Johnny ET Sheo

> **Objectif.** Les bots « entendent » ce que dit le streamer (micro), et **au plus un** des deux
> réagit en personnage. Aujourd'hui `shared/stream_listener.py` existe mais c'est un **squelette
> non câblé** : capture factice (`_capture_and_process` = `await asyncio.sleep(1)`), aucun bot ne
> l'instancie, deps commentées dans `requirements.txt`. Ce plan le rend réel, **derrière flag**,
> sans toucher au chat existant.
>
> **Décisions déjà cadrées** (cf. [[plan-twitch-v2]]) : écoute **continue + jugement** ; **1 seul
> flux micro** (hub unique) partagé Johnny+Sheo ; **arbitrage** (jamais 2 bots sur le même énoncé) ;
> STT **100 % local** sur le PC de stream (RTX 4060 Ti). Le plus lourd → fait en dernier, isolé.
>
> **Exigences dures :**
> - **Off par défaut** (`enable_voice_listen=False`) ; bots **toujours** fonctionnels si STT HS/absent.
> - **Anti-saturation** : toute réponse-voix passe par le plafond global `global_msg_timestamps`
>   (18/30 s) **+** un intervalle mini **global voix** (≥ 45 s, tous bots confondus).
> - **Cloisonnement/indépendance** ([[bots-independants]]) : imports défensifs, dégradation propre.
> - **Capture micro = Windows natif** (gotcha WSL2/Docker : le micro n'est pas exposé) → hub local.

---

## Phase 5.0 — Prérequis (à trancher AU DÉBUT)

### 5.0.1 Choix du moteur ASR (un seul, configurable `listen.mode`)
- **(C) faster-whisper — RECOMMANDÉ pour démarrer** : `pip install faster-whisper`, trivial sous
  Windows, `large-v3-turbo` en `int8` GPU (ou CPU). Déjà amorcé dans `stream_listener.py:19-24`.
- **(A) NIM Nemotron streaming** (gRPC localhost:50051, Docker Desktop+WSL2+NVIDIA Toolkit+`NGC_API_KEY`)
  et **(B) NeMo Python** (`nvidia/nemotron-3.5-asr-streaming-0.6b`, WSL2) : meilleurs (streaming
  < 100 ms, endpointing natif) mais lourds à installer → **après** que (C) valide la chaîne complète.

### 5.0.2 Dépendances (`requirements.txt`, sous le commentaire « STT optionnel »)
Décommenter au besoin : `sounddevice`, `numpy`, `faster-whisper`, **`websockets`** (le hub/clients
l'utilisent). Garder commenté ce qui ne sert pas au mode retenu. Ne **jamais** rendre ces deps
obligatoires (les autres bots/Docker ne les ont pas).

### 5.0.3 Micro
Le hub tourne **là où est le micro** (PC de stream, Windows natif). Si les bots sont en Docker, le
hub reste un **process Windows séparé** ; les bots s'y connectent en client WebSocket
(`ws://<host>:8765`). ⚠️ Docker→host : exposer/router le port (ou faire tourner le bot concerné en
natif). Noté pour [[plan-deploy-oracle]].

---

## Phase 5.1 — Capture réelle + ASR dans le hub (`shared/stream_listener.py`)

### 5.1.0 Bugs du squelette à corriger D'ABORD (découverts au test tuyauterie 2026-06-24)
1. **Découpler le serveur WebSocket des deps audio.** `start()` fait `if not DEPS_AVAILABLE: return`
   (`:44-46`) → impossible de lancer le hub sans `sounddevice`. Or la tuyauterie (WS + arbitrage) n'a
   pas besoin d'audio. → Ne gater QUE la capture/ASR sur `DEPS_AVAILABLE`, pas le démarrage du serveur
   WS. (Permet de tester l'arbitrage sans micro.)
2. **Signature handler `websockets` ≥ 11/16.** Le handler est `async def handler(websocket, path)`
   (`:67`) ; depuis websockets ≥ 11 il est appelé avec **un seul argument**. → passer à
   `async def handler(websocket)` et lire le chemin via `websocket.request.path` si besoin.
   (Env actuel = websockets 16.0, vérifié.) Idem vérifier `websockets.connect`/`serve` côté API 16.0.
3. Rappel : `_capture_and_process` est factice (`:99-107`) et le client n'est câblé à aucun bot.


Remplacer le stub `_capture_and_process` (`stream_listener.py:99-107`) par la vraie boucle :
- **Capture** : `sounddevice.InputStream` (16 kHz mono, frames PCM), pousser les frames dans une
  file asyncio. Garder le `DEPS_AVAILABLE` défensif déjà présent (`:11-17`).
- **Garde d'énergie anti-silence** : ignorer les frames sous un seuil RMS (évite de transcrire le
  silence/le souffle). Pas besoin de VAD lourd pour (C) ; (A)/(B) ont l'endpointing natif.
- **Segmentation** : accumuler jusqu'à une pause (silence > ~700 ms) → un **énoncé finalisé**.
- **Transcription** : mode (C) → `self.whisper_model.transcribe(pcm, language="fr")` (le modèle est
  déjà chargé dans `start()` `:51-58`). Mode (A) → client gRPC ; (B) → `conformer_stream_step`.
- **Diffusion** : sur énoncé finalisé **non vide** et de longueur mini (≥ ~3 mots, ignore « euh »),
  appeler `self.broadcast(text)` (déjà implémenté `:109-123`, hash + envoi à tous les clients).

> `StreamListenerHub` a déjà : serveur WebSocket (`:96`), `broadcast` (`:109`), arbitrage **claim**
> (`handler` `:74-89`, `claim_locks` : 1er arrivé gagne, `priority` écrase). **Ne pas réécrire** ça.

---

## Phase 5.2 — Lanceur du hub (nouveau : `run_stream_listener.py`, racine)

Petit script **autonome** lancé sur le PC de stream (1 seul, possède le micro) :
- Lit la config dashboard `data/twitch_config.json` (clé `listen` d'un bot « pilote », ex. johnny) :
  `mode`, `device`, `chunk_ms`, `min_interval`, `enabled` (kill-switch).
- Instancie `StreamListenerHub(port=8765, mode=…, device=…)`, `await hub.start()`, tourne tant que
  `enabled`. Si `enabled=false` → ne capture pas (kill-switch). Log clair, `try/except` deps absentes.
- **Ne dépend d'aucun bot** (autonomie). Doc d'usage en tête du fichier.

---

## Phase 5.3 — Câbler le client d'écoute dans `TwitchChatBot` (générique → Johnny+Sheo héritent)

Tout dans `shared/twitch_chat.py` pour que les 2 bots héritent (patron Phases 1-4).

### 5.3.1 Nouveaux params (`__init__` + `setup_twitch_chat`, propager comme les autres flags)
`enable_voice_listen: bool=False`, `voice_min_interval: float=45.0`, `voice_chance: float=0.5`,
`listen_port: int=8765`, `listen_host: str="localhost"`. Stocker en attributs. Ajouter
`self._last_voice_ts = 0`.

### 5.3.2 Lecture dashboard (réutiliser l'existant)
Dans `setup_twitch_chat`, après le bloc `dash = _load_dashboard_twitch_config(...)` (déjà présent,
`twitch_chat.py:1567`), lire `dash.get("listen")` : `enabled`→`enable_voice_listen`,
`min_interval`→`voice_min_interval`. (Le dashboard a déjà `listen` + endpoints `/api/twitch/listen/{bot}`.)

### 5.3.3 Démarrage de la tâche (dans `run()`, calqué sur `eventsub_task` `:411,429-430`)
```python
voice_task = None
...
if self.enable_voice_listen and voice_task is None:
    voice_task = asyncio.create_task(self._start_voice_listen())
```
À annuler proprement dans le `finally`/`stop()` (comme eventsub).

### 5.3.4 `_start_voice_listen` + handler d'énoncé
- Import défensif : `from shared.stream_listener import StreamListenerClient` (try/except → no-op log).
- Instancier `StreamListenerClient(bot_id, logger, on_transcript_received_callback=self._on_voice_transcript, port=self.listen_port)` et `await client.run()` (reconnexion/backoff déjà gérés `:144-175`).
- `async def _on_voice_transcript(self, text, text_hash)` :
  1. **Filtre longueur** (déjà filtré côté hub, re-garde ici).
  2. **Intervalle mini voix global** : `now - self._last_voice_ts < self.voice_min_interval` → drop.
  3. **Pertinence/gate** : si le **nom du bot** est prononcé (`self.trigger_re.search(text)`) →
     `priority=True` ; sinon gate proba `random.random() < self.voice_chance`.
  4. **Arbitrage** : `granted = await client.request_claim(text_hash, priority=...)` (déjà
     implémenté `:177-196`). Si `granted` est faux → **un autre bot a pris l'énoncé** → drop.
  5. **Plafond global** : purge + check `global_msg_timestamps` (18/30 s) comme `emit_callback`
     (`:1461-1474`). Si plein → log + drop.
  6. **Génération** : réponse courte en personnage (réutiliser le prompt court de
     `_generate_interjection` `:1346+`, en injectant `text` comme propos du streamer ; `max_tokens≈60`,
     `_strip_stage_directions`). Envoyer via `self.ws.send_str(f"PRIVMSG #{chan} :{reply}")` sur
     `self.channels[0]`, push `global_msg_timestamps`, set `self._last_voice_ts = now`.

> Le `text_hash` du claim = **même hash** que celui diffusé par le hub (`broadcast` `:112`) → l'arbitrage
> fonctionne entre Johnny et Sheo : le 1er qui claim gagne, le bot **nommé** est prioritaire.

### 5.3.5 Activation côté bots (`bot_johnny.py` ~`:442`, `bot_sheogorath.py` ~`:699`)
Ajouter aux appels `setup_twitch_chat(...)` : `enable_voice_listen=False` (défaut ; piloté par le
dashboard ou un flag). **Aucune logique propre** : tout est générique.

---

## Phase 5.4 — Garde-fous (saturation = risque élevé ici)
- Intervalle mini **global voix** ≥ 45 s (5.3.4 #2) **tous bots confondus** (chaque bot a son
  compteur, et l'arbitrage empêche le doublon par énoncé).
- Longueur d'énoncé mini (5.1) ; garde d'énergie anti-silence (5.1).
- **Kill-switch** = `listen.enabled=false` au dashboard (le hub ne capture pas) **et**
  `enable_voice_listen=false` (le bot ne se connecte pas). Compteur + logs de transcription.
- Repli : si LLM indispo → pas de réponse (pas de fallback scripté ici, on reste silencieux).

---

## Phase 5.5 — Dashboard « Écoute live » (déjà présent, juste vérifier le câblage)
- Le schéma `listen` (enabled/mode/device/chunk_ms/min_interval) + endpoints `GET/PUT
  /api/twitch/listen/{bot}` + la vue existent (Phase 6). **Vérifier** que la vue lit/écrit bien, et
  que 5.3.2 (bot) + 5.2 (hub) consomment ces valeurs. Le kill-switch doit couper net (au redémarrage
  du bot/hub — pas de hot-reload, cf. Hors périmètre).

---

## Vérifications (avant test live)
- `py_compile` : `shared/stream_listener.py`, `shared/twitch_chat.py`, `run_stream_listener.py`,
  `JohnnyBot/bot_johnny.py`, `Sheogorath/bot_sheogorath.py`.
- **Autonomie** : bots démarrent **sans** deps STT et **sans** hub (no-op propre, log « inactif »).
- **Test fonctionnel** : parler dans le micro → **1 seule** réponse (jamais Johnny ET Sheo) ;
  silence → **0** transcription/0 appel ASR ; prononcer le nom d'un bot → c'est lui qui répond
  (priorité) ; respect de l'intervalle ≥ 45 s ; `listen.enabled=false` → plus rien.
- **Anti-saturation** : voix + mentions + events en rafale ≤ 18 envois/30 s par bot.

## Hors périmètre
- **Hot-reload** du kill-switch (couper sans redémarrer) : nécessiterait un watcher ; ici on applique
  au redémarrage. Noté.
- TTS / voix clonée (le bot répond en **texte** dans le chat, pas en voix) — parqué
  ([[feature-gpu-parkee-oracle]]).
- Généralisation aux 4 autres bots : plus tard.

## Rollback
Phase isolée : `enable_voice_listen=False` (défaut) + hub non lancé = aucun impact sur le chat.
`shared/stream_listener.py` + `run_stream_listener.py` supprimables sans toucher au reste.
