# PLAN — Correctifs Phase 5 écoute live : réponse SUR NOM uniquement + arbitrage/intervalle au hub

> **Contexte.** La Phase 5 (écoute live STT) est commitée (`e3975fd`, `b83e1f6`, `54f6c28`). Un test
> end-to-end du pipeline (vrai hub + 2 clients, micro/Whisper et LLM mockés) a révélé **2 bugs** qui
> violent l'exigence dure « **au plus 1 bot répond par énoncé** » / « **intervalle ≥ 45 s tous bots
> confondus** » ([[plan-twitch-phase5-stt]], [[plan-twitch-v2]]) :
>
> - **Bug B — double réponse sur priorité (19/20).** Quand le streamer prononce le nom d'un bot, le
>   bot non-nommé réclame le claim en premier (granted), puis le bot nommé l'**écrase** (granted aussi)
>   → **les deux** envoient. Le « priority override » est intrinsèquement racy en modèle broadcast.
> - **Bug C — intervalle non global (1 au lieu de 0).** Johnny et Sheo sont des **processus séparés**
>   (compteurs `_last_voice_ts` / `global_msg_timestamps` **non partagés**). « johnny… » puis « sheo… »
>   à 1 s d'intervalle → 2 réponses. Le **seul** point partagé est le **hub** ; il n'impose aucun
>   intervalle global.
>
> **Décision produit (utilisateur, 2026-06-25).** Un bot **ne réagit à la voix QUE s'il entend un de
> ses propres noms** (on **supprime** la gate probabiliste `voice_chance`). Conséquence : pour un
> énoncé donné, **au plus un** bot est nommé → plus de course → **Bug B disparaît** sans « priority ».
> Le **Bug C** se règle en déplaçant l'arbitrage + l'intervalle **au hub** (point partagé unique).
>
> **Cadre.** Correctif isolé, off par défaut inchangé (`enable_voice_listen=False`). Ne touche ni au
> chat existant, ni à la capture audio, ni au dashboard. `py_compile` + autonomie ([[bots-independants]])
> à reconfirmer.

---

## Tâche 1 — Bot : réagir UNIQUEMENT sur son nom (`shared/twitch_chat.py`, `_on_voice_transcript` `:1558-1598`)

Remplacer le bloc gate (`:1571-1576`) :
```python
priority = False
if self.trigger_re.search(text):
    priority = True
    self.logger.info(...)
elif random.random() >= self.voice_chance:
    return
```
par une **garde stricte sur le nom** (plus de hasard, plus de `priority`) :
```python
# Le bot ne réagit à la voix QUE si l'un de ses noms est prononcé (décision produit).
if not self.trigger_re.search(text):
    return
```
- Adapter l'appel de claim (`:1581`) : `granted = await self.voice_client.request_claim(text_hash)`
  (sans `priority`). Le claim reste comme **filet de sécurité** pour le cas rare où **deux** noms
  figurent dans le même énoncé (« johnny et sheo, vous en pensez quoi ») → premier arrivé gagne.
- **Ne pas** retirer : le filtre longueur (`:1562-1564`), l'intervalle bot-side (`:1566-1569`, défense
  locale, garde le MÊME bot de répéter), le plafond `global_msg_timestamps` 18/30 s (`:1586-1590`),
  la génération + envoi (`:1592-1598`).
- **`voice_chance`** devient inutilisé : retirer l'attribut/param `voice_chance` du `__init__`
  (`:305`, `:328`) **et** ne plus le câbler ; idem l'import `random` si plus utilisé ailleurs (vérifier
  `grep -n "random" shared/twitch_chat.py` — il sert ailleurs, donc **garder l'import**, retirer juste
  l'usage `voice_chance`). Si retirer le param casse un appelant, le garder en param mort documenté
  « (obsolète, écoute sur nom) » — au choix, mais **aucune gate aléatoire** ne doit subsister.

## Tâche 2 — Hub : un seul grant par énoncé + intervalle GLOBAL (`shared/stream_listener.py`, handler claim `:70-85`)

Le hub est le **seul** état partagé entre Johnny et Sheo → c'est lui qui doit garantir « 1 réponse
par énoncé » ET « ≥ 45 s tous bots confondus ».

### 2.1 `__init__` (`:32-41`)
Ajouter : `voice_min_interval: float = 45.0` en param ; `self.voice_min_interval = voice_min_interval` ;
`self.last_grant_ts = 0.0`.

### 2.2 Logique de claim (`:70-85`) — remplacer entièrement la branche `action == "claim"`
Supprimer le « priority override » (`elif priority and current_claim != bot_id:` `:80-83`). Nouvelle
logique (1 seul grant par hash + verrou d'intervalle global) :
```python
if action == "claim":
    text_hash = data.get("hash")
    bot_id = data.get("bot_id")
    now = time.time()
    if now - self.last_grant_ts < self.voice_min_interval:
        granted = False                      # intervalle global (tous bots confondus)
    elif text_hash not in self.claim_locks:
        self.claim_locks[text_hash] = bot_id # 1er arrivé gagne, jamais d'écrasement
        self.last_grant_ts = now
        granted = True
    else:
        granted = False                      # déjà pris par un autre bot
    await websocket.send(json.dumps(
        {"type": "claim_response", "hash": text_hash, "granted": granted}))
    logger.info(f"{'🏆 Claim accordé à' if granted else '⛔ Claim refusé à'} {bot_id} ({text_hash})")
```
- `time` est déjà importé (`stream_listener.py:6`).
- Le champ `priority` envoyé par le client peut rester (ignoré). `claim_locks` n'est jamais purgé
  aujourd'hui : acceptable (un hash = un énoncé unique, croissance lente). **Ne pas** ajouter de purge
  dans ce correctif (hors périmètre).

> Effet combiné : dans le même énoncé, seul le 1er claim passe (Bug B couvert même sans la garde nom) ;
> après un grant, **tout** claim (n'importe quel bot/énoncé) est refusé pendant 45 s (Bug C réglé).

## Tâche 3 — Lanceur : propager l'intervalle au hub (`run_stream_listener.py`)

- `load_listen_config` (`:36-53`) : ajouter la lecture `"min_interval": float(listen_cfg.get("min_interval", 45.0))`
  (try/except → 45.0 par défaut).
- `main` (`:66`) : `hub = StreamListenerHub(port=8765, mode=cfg["mode"], device=cfg["device"], voice_min_interval=cfg["min_interval"])`.

---

## Vérifications (avant test live)
1. `py_compile` : `shared/stream_listener.py`, `shared/twitch_chat.py`, `run_stream_listener.py`,
   `JohnnyBot/bot_johnny.py`, `Sheogorath/bot_sheogorath.py`.
2. **Autonomie** : bots démarrent sans deps STT et sans hub (no-op, `enable_voice_listen=False`).
3. **Test fonctionnel pipeline (sans micro)** — rejouer le harnais (vrai `StreamListenerHub` avec
   `DEPS_AVAILABLE=False`, 2 vrais `StreamListenerClient`, `_on_voice_transcript` réel, LLM+`ws.send_str`
   mockés). Résultats **attendus après correctif** :
   - **A** énoncé neutre (aucun nom) → **0** réponse (avant : 1). Les bots ne parlent que nommés.
   - **B** « …johnny… » → **johnny seul** répond, sheo muet, **0 double** (avant : 19/20).
   - **C** « …johnny… » puis « …sheo… » à < 45 s → **1 seule** réponse (la 2ᵉ refusée par le hub).
   - **D** johnny déjà à 18/30 s → johnny muet.
   Réf. harnais : `scratchpad/test_pipeline.py` (à adapter : retirer la gate `voice_chance`, attendre
   A=0 et C: 2ᵉ=0).

## Hors périmètre
- Purge de `claim_locks` ; hot-reload du kill-switch ; TTS ; généralisation aux 4 autres bots.
- Gotcha env **numpy 2 vs faster-whisper/ctranslate2/torch** (warning au chargement Whisper, mode C) :
  à régler sur le PC de stream avant le test live réel (`pip install "numpy<2"` ou rebuild). Sans impact
  sur la tuyauterie/arbitrage testés ici. Noté ([[plan-twitch-phase5-stt]]).

## Rollback
Correctif local aux 3 fichiers. Revenir aux commits `e3975fd`/`b83e1f6` rétablit l'état précédent
(avec les 2 bugs). `enable_voice_listen=False` (défaut) = aucun impact tant que non activé.
