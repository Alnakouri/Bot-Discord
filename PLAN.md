# PLAN — Sugar sur Twitch : le ton face à une excuse et un message court · Annonces automatiques

Rédaction : Claude, le **2026-09-23** (soir). Exécution : **Antigravity**, sauf les étapes
marquées **[Ahmed]**. Le plan précédent (réactions de Sheogorath) est livré (`481d712`,
CI verte, en prod) ; lisible dans git (`481d712:PLAN.md`).

Deux parties **indépendantes** : on peut livrer B sans A et inversement. Un commit par partie.

---

# PARTIE A — Sugar sur Twitch : ne plus se moquer d'une excuse ni d'un message court

## Ce qui a été constaté (23/09, 21:53-22:01, `#chaine_du_dev`, Ahmed)

Journal `data/decisions.db` (décision `ton`, `voie=twitch`) et chat :

| message d'Ahmed | ton classé | consigne donnée au modèle | réponse de Sugar |
|---|---|---|---|
| `sugar` | neutral | `_DIRECTIVE_NEUTRAL` | « Une simple mention de mon nom sans rien autour, c'est un peu sec, non ? … » |
| `@compte_bot_sugar dsl` | apology ✅ | **AUCUNE** (`""`) | « Un « dsl » lâché comme ça, on dirait une pastille sans sucre : un peu fade… » |
| `@compte_bot_sugar c'est mechant =(` | neutral | `_DIRECTIVE_NEUTRAL` | « Un simple « c'est méchant » alors que je n'ai fait que respirer, tu manques un peu de consistance… » |

La regex a bien classé les trois. Trois causes, toutes après le classement :

1. **L'excuse ne reçoit AUCUNE consigne.** `SugarBot/sugar_grudge.py:156` `tone_directive`
   rend `""` pour `apology` comme pour `aggro` (« le mordant est OK face à une hostilité »).
   Même chose sur Discord quand la personne n'a **aucune** rancune
   (`GrudgeBook`, l.306-311 : `return ""  # aggro/excuse sans rancune`). Une excuse est
   traitée comme une attaque.
2. **La consigne neutre NOMME ce qu'elle interdit** (l.129-134) : « ne la reprends pas sur
   des broutilles (minuscules, orthographe, **longueur** de son pseudo) ». Même mécanisme
   que le « XVe siècle » du 23/09 : ce qui est écrit dans le prompt ressort. La 1re réponse
   commente exactement la longueur du message.
3. **Elle recopie sa propre ossature** : une fois la 1re réponse faite en « Un « X » + jugement
   sur la forme », les deux suivantes l'imitent (ses répliques reviennent dans l'historique ;
   l'anti-répétition de `shared/twitch/llm.py:265-275` interdit les MOTS, pas l'OSSATURE).
   ⚠️ Cette partie ne touche **pas** `shared/` : on mesure d'abord si 1 et 2 suffisent.

## LOT A0 — Sonde, et mesure AVANT (sur le code d'aujourd'hui)

Nouveau `tools/sonde_ton_twitch.py`, sur le modèle de `tools/sonde_phrase_de_lien.py`
(mêmes `charger()` — clés de **Sugar seule**, depuis `SugarBot/` — même option `--timeout`
qui ne desserre que la borne de l'appel, même `--tete gemini`). Différence : le faux bot
hérite de `LlmMixin` (`shared/twitch/llm.py:200`) et la sonde appelle le **vrai**
`_generate_response(channel, author, message)`. Attributs à poser sur le faux bot (lus par
`_generate_response`, l.201-382) : `bot_id="sugar"`, `bot_label`, `personality_prompt`
(= `sugar_data.PERSONALITY_PROMPT`), `system_prompt_provider=None`, `key_manager`,
`mistral_client/groq_client/nvidia_client=None`, `injection_hits=collections.defaultdict(int)`,
`enable_viewer_memory=False`, `viewer_facts={}`, `recent_self_responses={}`,
`channel_recent={}`, `histories={}`, `extra_recent_provider=None`, `logger` (comme la sonde
existante), et **`tone_directive_provider = SugarBot.sugar_grudge.tone_directive`** — la
VRAIE fonction, pas une copie (pas `_ton_twitch` : elle journaliserait dans `data/`).
Si `_generate_response` lit un autre attribut, l'ajouter : **lire la méthode, pas deviner**.

Deux scénarios, `--n 18` chacun (état du faux bot **remis à zéro** entre deux tours) :

- **`isole`** : un message seul, sur un bot neuf. Trois sous-séries de 18 :
  `sugar`, `@compte_bot_sugar dsl`, `@compte_bot_sugar c'est mechant =(`.
- **`conversation`** : les trois messages **à la suite**, même auteur, même canal, sans
  remise à zéro entre eux (c'est l'historique qui propage l'ossature). 18 conversations.

Sortie : chaque réponse en clair, numérotée, avec le message qui l'a provoquée.
Fichiers de sortie dans un dossier temporaire, **jamais commités**.

Lancer AVANT de toucher au code :
`PYTHONIOENCODING=utf-8 uv run --no-project --python 3.11 --with-requirements requirements.txt -- python tools/sonde_ton_twitch.py --scenario isole --n 18 --timeout 30 > avant_isole.txt`
(et `--scenario conversation`). ⚠️ Jamais pendant un live de `ma_streameuse` : même quota
que la prod de Sugar.

## LOT A1 — Une consigne pour l'excuse

`SugarBot/sugar_grudge.py`, **juste après** `_DIRECTIVE_NEUTRAL = (...)` (fin l.134) :

```python
# ⚠️ 23/09 : l'excuse ne recevait AUCUNE consigne (traitee comme une attaque) : sur Twitch,
# un « dsl » a recu « on dirait une pastille sans sucre ». Une excuse appelle la grace.
_DIRECTIVE_APOLOGY = (
    "\n[TON] Cette personne s'excuse auprès de toi : accepte ses excuses tout de suite, "
    "avec grâce et un brin de malice, puis passe à autre chose avec elle comme si de rien "
    "n'était. Tu es une reine qui pardonne, pas une juge.")
```

`tone_directive` (l.156-168) : ajouter, entre `neutral` et `return ""` :

```python
    if tone == "apology":
        return _DIRECTIVE_APOLOGY
```

et mettre la docstring à jour (« aggro → '' : persona brute » ; `apology` a sa consigne).

`GrudgeBook` (l.306-311), même ajout avant le `return ""`, et corriger le commentaire de
ce `return` en `# aggro sans rancune → persona brute`. ⚠️ Ce chemin est celui de **Discord**
quand la personne n'a aucune rancune : le changement vaut donc aussi sur Discord, et c'est
voulu (même défaut). Le chemin de rédemption (`_DIRECTIVE_REDEEMED`, rancune > 0) ne bouge pas.

## LOT A2 — La consigne neutre dit quoi FAIRE, sans nommer ce qu'elle interdit

`SugarBot/sugar_grudge.py:129-134`, **remplacer** le texte de `_DIRECTIVE_NEUTRAL` par :

```python
_DIRECTIVE_NEUTRAL = (
    "\n[TON] Message neutre ou anodin, cette personne ne t'a rien fait : sois AVENANTE et "
    "chaleureuse, taquine tout au plus. Rebondis sur le SUJET de son message ; s'il n'y en "
    "a pas (juste ton nom, un mot, une réaction), prends-le comme une invitation à discuter "
    "et lance toi-même la conversation. Tu ne sors tes griffes QUE si on te cherche "
    "vraiment ; sinon, garde ton esprit mais range le venin.")
```

⚠️ Garder le début exact `"\n[TON] Message neutre"` : `tests/test_sugar_grudge.py:344` le teste.
⚠️ Aucun des mots « longueur », « forme », « court », « sec », « orthographe » dans le texte.

## LOT A3 — Tests

`tests/test_sugar_grudge.py`, dans `test_tone_directive` (l.335) : ajouter
`self.assertTrue(tone_directive("dsl").startswith("\n[TON] Cette personne s'excuse"))`
et `self.assertEqual(tone_directive("ferme la"), "")` reste vrai (aggro).
Un test sur `GrudgeBook` : une personne **sans rancune** qui écrit « désolé » reçoit
`_DIRECTIVE_APOLOGY` (s'inspirer des tests existants du fichier pour construire le carnet
dans un fichier temporaire — jamais dans `data/`). Et un verrou :
`for mot in ("longueur", "orthographe", "minuscules"): assert mot not in _DIRECTIVE_NEUTRAL.lower()`.

## LOT A4 — Mesure APRÈS, critères fixés MAINTENANT

Mêmes commandes que A0, sur le code modifié. **Lecture réponse par réponse**, critères :

| critère | seuil |
|---|---|
| `dsl` (isolé) : accepte l'excuse, sans moquerie de l'excuse | **≥ 15/18** |
| `sugar` (isolé) : commente la forme/brièveté du message (« sec », « sans rien autour », « lâché comme ça »…) | **≤ 2/18** |
| `c'est mechant =(` (isolé) : nouvelle pique sur la PERSONNE | **≤ 4/18** |
| conversation : réponses qui CITENT le message entre « » ou "" pour le juger | **≤ 6/54** |
| réponses vides / gabarit / erreur | ≤ 2 par série |

Plancher de bruit à n = 18 : ±3. **Décision** : tout passe → LOT A5. `dsl` ou `sugar` échoue
→ ne pas livrer, rapporter les chiffres AVANT/APRÈS à Ahmed. Seule la conversation échoue
→ livrer A1-A3 (gain réel) et rapporter : l'ossature se traitera dans `shared/twitch/llm.py`
avec son propre plan.

## LOT A5 — Vérifier, livrer

pyflakes sur les fichiers touchés, suite complète (un seul pytest), commit, push,
`gh run list --limit 1` → `success`. Prod **[Ahmed : hors live]** : `docker restart bot-sugar`.

---

# PARTIE B — Annonces automatiques d'un lien (façon « timers » de WizeBot/Nightbot)

## Ce qui est demandé (Ahmed, 23/09)

Dans le dashboard, sur chaque ligne de « Commandes de liens personnalisées » : un temps
**choisi à la main** (en minutes) ; le bot poste alors le lien tout seul à cet intervalle.

## Comment ça marche (à respecter exactement)

- **Pas de boucle de fond.** Comme les interjections (`shared/twitch/dispatch.py:501`), le
  contrôle se fait **à la réception d'un message de chat** (branche passive). Conséquence
  voulue : un chat vide ne reçoit rien.
- Une annonce part sur un canal quand **les trois** sont vrais :
  1. au moins `auto_minutes` minutes depuis la dernière annonce de ce lien sur ce canal
     (au démarrage, le compteur part du **premier message vu** : pas d'annonce immédiate) ;
  2. au moins `auto_min_messages` messages de chat passifs sur ce canal depuis (0 = temps seul) ;
  3. **le canal est EN DIRECT** (`HelixClient.get_current_game(chan, live_only=True)` rend
     un nom non `None` — « Just Chatting » compte comme en direct). Hors direct : rien.
- **Le texte** = exactement ce que rendrait la commande : on appelle le **même callback**.
  Champ « Message » vide → la phrase du bot (cache de 15 min compris) ; rempli → ce texte.
- **Au plus une action spontanée par message**, comme le reste de la branche passive, et le
  budget global (`global_msg_timestamps` < 14) est respecté.

## LOT B1 — Backend du dashboard

`dashboard/backend/twitch_config.py`, `update_link_commands` (l.295). Avant le
`cleaned_items.append({...})` (l.388), lire et valider deux champs :

```python
            # Annonce automatique (23/09) : minutes entre deux annonces, 0 = eteinte.
            # Plancher de 5 min : une faute de frappe (« 1 ») ne doit pas faire spammer le chat.
            try:
                auto_minutes = int(item.get("auto_minutes") or 0)
                brut_msgs = item.get("auto_min_messages")
                auto_min_messages = 5 if brut_msgs in (None, "") else int(brut_msgs)
            except (TypeError, ValueError):
                raise ValueError(f"Les valeurs d'annonce auto de '{cmd}' doivent être des nombres entiers.")
            if auto_minutes < 0 or auto_min_messages < 0:
                raise ValueError(f"Les valeurs d'annonce auto de '{cmd}' ne peuvent pas être négatives.")
            if 0 < auto_minutes < 5:
                raise ValueError(f"L'annonce auto de '{cmd}' : 5 minutes minimum (0 pour l'éteindre).")
```

et ajouter `"auto_minutes": auto_minutes, "auto_min_messages": auto_min_messages` au dict
ajouté. ⚠️ Une config déjà enregistrée SANS ces clés doit rester valide partout (lecture
par `.get(..., défaut)`).

## LOT B2 — Frontend du dashboard

1. `dashboard/frontend/index.html`, en-tête du tableau (l.~486-491) : ajouter **avant**
   « Action » deux colonnes : `Auto (min)` (min-width 90px) et `Msgs min` (min-width 80px).
   Sous le tableau, compléter la ligne ⚠️ : « Auto (min) : le bot poste le lien tout seul
   toutes les N minutes pendant un live, si le chat a eu au moins « Msgs min » messages
   depuis (0 = éteint, 5 min minimum). »
2. `dashboard/frontend/js/app.js` :
   - `renderLinksTable` (l.1489) : `colspan="6"` → `colspan="8"` ; passer
     `link.auto_minutes, link.auto_min_messages` à `addLinkRow`.
   - `addLinkRow` (l.1501) : deux paramètres de plus (`autoMinutes = 0, autoMinMessages = 5`),
     deux `<td>` avec `<input type="number" min="0" step="1" class="link-auto-minutes-input form-input">`
     et `link-auto-msgs-input`, avant la cellule du bouton ; valeurs échappées par
     `escapeHtml(String(...))`.
   - `saveLinkCommands` (l.1531) : lire les deux champs
     (`parseInt(... ) || 0` pour les minutes ; vide → `5` pour les messages) et les
     ajouter à l'objet poussé.

## LOT B3 — Le bot reçoit la liste des annonces

`shared/twitch_chat.py` :

1. Juste après `link_auto = {}` (l.402) : `link_timers = []`.
2. Dans la boucle, juste après `link_auto[cmd] = message_auto` (l.460) :

```python
        try:
            auto_min = int(entry.get("auto_minutes") or 0)
            auto_msgs = int(entry.get("auto_min_messages", 5) or 0)
        except (TypeError, ValueError):
            auto_min, auto_msgs = 0, 5
        if auto_min >= 5:
            link_timers.append({"cmd": cmd, "every": auto_min * 60,
                                "min_msgs": max(auto_msgs, 0), "callback": callback})
```

3. Dans le résumé journalisé (l.~480, boucle `for cmd in link_cmds`) : si ce `cmd` a un
   timer, ajouter `f"auto {minutes} min / {msgs} msgs"` aux `details`.
4. Juste après `bot_ref["bot"] = bot` (l.543) : `bot.link_timers = link_timers`.
5. `TwitchChatBot.__init__`, près de `self.cohost_channels = ...` (l.164) :
   `self.link_timers = []` et `self._etat_timers = {}` (clé `(canal, cmd)` →
   `{"depuis": horodatage, "msgs": int}`).

## LOT B4 — Le déclenchement

`shared/twitch/dispatch.py` :

1. Branche passive, **juste après** `categorie_jeu = self._question_de_jeu(text, "passif")`
   (l.~433) : compter le message pour chaque timer de ce canal :

```python
        for t in getattr(self, "link_timers", []):
            etat = self._etat_timers.setdefault((chan_lower, t["cmd"]),
                                                {"depuis": time.time(), "msgs": 0})
            etat["msgs"] += 1
```

2. **Entre** l'option A.2 (co-host) et l'option B (accueil), l.~495 :

```python
        # Option A.3 : annonce automatique d'un lien (reglee dans le dashboard, 23/09)
        if not spontaneous_sent and getattr(self, "link_timers", None):
            spontaneous_sent = await self._try_link_timer(chan, ws)
```

3. Nouvelle méthode, à côté de `_try_interjection` (l.579) :

```python
    async def _try_link_timer(self, chan: str, ws) -> bool:
        """Poste un lien regle en « auto » dans le dashboard, si son heure est venue.

        Trois conditions : l'intervalle, le nombre de messages depuis la derniere annonce,
        et le DIRECT (hors live, le chat d'une chaine ne doit pas recevoir de pub). Le
        texte est celui de la commande elle-meme : meme callback, meme cache.
        """
        now = time.time()
        chan_lower = chan.lower()
        for t in self.link_timers:
            etat = self._etat_timers.get((chan_lower, t["cmd"]))
            if not etat or now - etat["depuis"] < t["every"] or etat["msgs"] < t["min_msgs"]:
                continue
            if not await self._canal_en_direct(chan_lower):
                return False
            while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
                self.global_msg_timestamps.popleft()
            if len(self.global_msg_timestamps) >= 14:
                return False
            try:
                cb = t["callback"]
                res = await cb("timer", "") if asyncio.iscoroutinefunction(cb) else cb("timer", "")
            except Exception as e:
                self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] annonce auto !{t['cmd']} : {e}")
                return False
            etat["depuis"], etat["msgs"] = now, 0
            if not res:
                return False
            self.global_msg_timestamps.append(now)
            self.logger.info(f"⏰ [TWITCH_CHAT:{self.bot_id}] Annonce auto !{t['cmd']} sur #{chan_lower}")
            await send_chat_safe(ws, chan, res, bot_id=self.bot_id, logger=self.logger)
            return True
        return False

    async def _canal_en_direct(self, chan: str) -> bool:
        """Vrai si CE canal est en direct. Faux au moindre doute (pas d'identifiants, erreur)."""
        if not getattr(self, "client_id", None) or not getattr(self, "client_secret", None):
            return False
        try:
            from shared.twitch.game_info import HelixClient
            if getattr(self, "_helix_client", None) is None:
                self._helix_client = HelixClient(self.client_id, self.client_secret)
            nom, _ = await self._helix_client.get_current_game(chan, live_only=True)
            return nom is not None
        except Exception as e:
            self.logger.debug(f"[TWITCH_CHAT:{self.bot_id}] direct indisponible pour #{chan} : {e}")
            return False
```

⚠️ Vérifier que `asyncio`, `time` et `send_chat_safe` sont déjà importés dans `dispatch.py`
(ils le sont pour `_handle_command`, l.~520-560).
⚠️ `_canal_en_direct` vérifie **le canal où le message arrive**, pas `channels[0]` : un bot
présent sur deux chaînes ne poste que sur celle qui est en live.
⚠️ Hors direct, l'état n'est **pas** remis à zéro : l'annonce partira dès que le live
commence et qu'un message arrive.

## LOT B5 — Tests

1. Backend (`tests/` : là où `update_link_commands` est déjà testé, sinon nouveau fichier) :
   `auto_minutes` 20 conservé ; absent → 0 ; `-1` refusé ; `3` refusé ; `"abc"` refusé ;
   `auto_min_messages` absent → 5 ; `0` accepté.
2. `shared/twitch_chat.py` : dans `tests/test_twitch_features.py` (qui teste déjà les
   `link_commands`), une config avec `auto_minutes: 20` → `bot.link_timers` a une entrée
   `every == 1200` ; `auto_minutes: 0` → liste vide.
3. `_try_link_timer`, faux bot `DispatchMixin` (comme `tools/sonde_phrase_de_lien.py:faux_bot`),
   `send_chat_safe` patché, `_canal_en_direct` remplacé par un `AsyncMock` :
   - avant l'intervalle → rien envoyé ;
   - intervalle passé mais `msgs < min_msgs` → rien ;
   - les deux OK mais hors direct → rien, état **non** remis à zéro ;
   - les deux OK et en direct → envoyé une fois, état remis à zéro, un 2e appel immédiat → rien ;
   - `min_msgs = 0` → l'intervalle seul suffit.
   Horloge : patcher `time.time` du module `dispatch`, jamais de `sleep`.

## LOT B6 — Vérifier, livrer

pyflakes sur les fichiers touchés, suite complète (un seul pytest), commit, push,
`gh run list --limit 1` → `success`.

## LOT B7 — Prod **[Ahmed : hors live]**

1. Redémarrer le **dashboard** (le backend lit le nouveau schéma).
2. Dans « Commandes de liens personnalisées » de Sugar : `Auto (min)` = la valeur voulue,
   `Msgs min` = 5 (ou autre), Enregistrer.
3. `docker restart bot-sugar`. Dans `docker logs --since 5m bot-sugar`, la ligne
   `🔗 … Commandes de lien armees : !discord (… auto N min / 5 msgs)`.
4. Au live suivant : la ligne `⏰ [TWITCH_CHAT:sugar] Annonce auto !discord sur #ma_streameuse`,
   suivie du `📤 Envoyé`.

⚠️ **[Ahmed]** Dans la même ligne du dashboard, l'alias est `ma_streameuse` : `!ma_streameuse`
poste donc le lien Discord. Si ce n'est pas voulu, vider le champ Alias.

---

## RESTE DES PLANS PRÉCÉDENTS

- **LOT 7 du 22/09 [Ahmed]** — recréer `.venv` en 3.11 (aujourd'hui 3.13 sans pyflakes) :
  `uv venv --python 3.11 .venv` puis
  `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`.
- **Question ouverte** : la borne de 300 ms de Laya (Laya est GARDÉ, décision d'Ahmed du 23/09).
- **Décret de Sheogorath** (constaté le 23/09) : 4 phrases pour « 1-2 » demandées ; les trois
  thèmes nommés dans le prompt (`bot_sheogorath.py:1129`) récités d'affilée ; titre > 32
  car. coupé en « … ». Plan à écrire si Ahmed le veut.
- **À lire après le live du 23/09** : les `!discord` de Sugar et Johnny (première mesure
  réelle de `2bb82b5`).

## INTERDITS DE CE PLAN

- Aucun `.env`, `.master_key`, `.env.encrypted`, ni base de `data/` touché — y compris
  `data/twitch_config.json` : c'est le dashboard qui l'écrit, pas l'exécutant.
- Aucune clé d'un bot utilisée pour un autre (la sonde A0 charge les clés de Sugar seule).
- Aucun import entre bots ; aucune factorisation. `SugarBot/sugar_grudge.py` reste à Sugar.
- Pas de boucle de fond (`asyncio.create_task` + `while`) pour les annonces : déclenchement
  à la réception d'un message, comme les interjections.
- **Un seul `pytest` à la fois.** Aucun lot « livré » tant que la CI n'est pas `success`.
