# PLAN — Twitch : (1) commandes « liens » par bot + (2) le bot répond aux questions sur le jeu en cours

## Contexte
Deux features Twitch demandées par le user (décisions arrêtées 2026-07-01/02). Tout passe par
l'infra **`shared/twitch/`** existante (bénéficie aux 6 bots), config pilotée par le **dashboard**
(`data/twitch_config.json`). Respecter [[bots-independants]] (chaque bot démarre seul, shared/ optionnel)
et la règle « **0 outil agentique sur Twitch** » (répondre = un message de chat normal, rien d'autre).
Le silence entre bots reste garanti (cf. [[plan-silence-total-bots]] : `if message.author.bot: return`,
`TWITCH_PEER_BOTS`). **Aucune modif côté Discord** (bot_*.py Discord, *_data.py, *_llm.py inchangés).

---

## FEATURE 1 — « Espace liens » par bot (commandes configurables au dashboard)

**But :** des commandes chat type `!discord` → lien du serveur, `!twitter`, `!yt`… configurables
**par bot** depuis le dashboard, **sans toucher au code d'un bot**. Réutilise l'infra `!cmd` existante
(`_handle_command`, dispatch.py:112 : cooldowns 3 s user / 5 s cmd + rate-limit + `send_chat_safe`).
Une commande lien = renvoie juste une string (0 LLM, 0 réseau).

### 1.A — Schéma config (`data/twitch_config.json`)
Ajouter par bot une clé `link_commands` (liste, défaut `[]`) :
```json
"link_commands": [
  { "cmd": "discord", "url": "https://discord.gg/xxxx", "label": "Serveur Discord",
    "message": "Rejoins la communauté : {url}", "aliases": ["serveur"] }
]
```
- `cmd` (obligatoire), `url` (obligatoire). `message` optionnel avec placeholder `{url}` (défaut :
  `"{label} : {url}"` ou juste `"{url}"`). `label` et `aliases` optionnels.
- Normaliser `cmd`/`aliases` : minuscules, sans `!` ni espaces.

### 1.B — Enregistrement runtime (partagé, 1 seul point → les 6 bots)
Dans **`shared/twitch_chat.py`** `setup_twitch_chat`, **après** `dash = _load_dashboard_twitch_config(...)`
(l.291) et **avant** `return TwitchChatBot(...)` (l.363) :
1. Lire `dash.get("link_commands") or []`.
2. Pour chaque entrée valide, construire un callback synchrone `lambda author, args, e=entry: format(...)`
   qui renvoie le message formaté (attention à la capture de boucle : lier `e=entry`).
3. Fusionner dans le dict `commands` **sans écraser une commande native du bot** (les built-ins
   `!decret`, `!fromage`… gagnent) : `commands = {**link_cmds, **(commands or {})}`. De même pour les
   alias. Logguer les collisions ignorées (`⚠️ [TWITCH_CHAT:{bot}] link_command !{cmd} ignorée (collision)`).
4. **Garde noms réservés** : refuser d'enregistrer un lien dont le `cmd`/alias percute un nom réservé
   (liste courte : `decret`, `decree`, `fromage`, `cheese`, `folie`, `faveur`, `favor`, `classement`,
   `leaderboard`, `humeur`, + noms de jeux Feature 2). Log + skip.
5. Passer `commands`/`command_aliases` enrichis à `TwitchChatBot(...)`.
> Ainsi **aucun bot_*.py n'est modifié** : les liens marchent pour les 6 via la config seule.

### 1.C — Dashboard (backend + frontend)
- **Backend `dashboard/backend/twitch_config.py`** : dans le schéma par bot, garantir la clé
  `link_commands` (défaut `[]`, comme `chat_channels` l.68). Ajouter
  `get_link_commands(bot_id)` et `update_link_commands(bot_id, items)` (valide/normalise/dédupe :
  `cmd` non vide, `url` non vide, filtre noms réservés côté serveur aussi).
- **Endpoints API** (là où sont exposés `update_chat_channels`/reward_map) : `GET`/`POST` link_commands.
- **Frontend** (section Twitch du bot, à côté des chaînes / reward_map) : petit tableau éditable
  (cmd | URL | message optionnel | aliases) + boutons add/remove/save. Modif = prise en compte au
  **redémarrage du bot** (comme les autres réglages twitch_config), pas de hot-reload requis.

### 1.D — Tests Feature 1
- `test_link_commands_registered` : une entrée config → commande présente dans le dict + renvoie le
  message formaté avec l'URL.
- `test_link_command_collision_skipped` : `cmd="decret"` → NON enregistré (built-in préservé).
- `test_link_command_alias` : alias résolu vers la bonne commande.

---

## FEATURE 2 — Le bot répond aux questions des viewers sur le jeu en cours (faits via IGDB)

**But :** quand un viewer demande, sur une chaîne où le bot est présent, des infos sur le jeu streamé
(plateforme(s), genre, studio/éditeur, solo/multi, date de sortie, « de quoi ça parle »), le bot répond
**dans sa persona**, en s'appuyant sur des **faits IGDB** (pas d'invention). **PRIX = hors scope** (abandonné).

### 2.A — Source des faits : Helix (jeu courant) → IGDB (faits)
Nouveau module **`shared/twitch/game_info.py`** (0 dépendance nouvelle : `aiohttp` déjà utilisé) :
- **Jeu courant** : `game_name`/`game_id` via Helix `GET /helix/streams?user_login={chan}` (patron
  `TwitchClient.get_streams`, twitch_announcer.py:74). Si la chaîne est offline → fallback
  `GET /helix/channels?broadcaster_id=...` (game_name dispo hors live ; résoudre l'id via
  `/helix/users?login=`). Cache `game_name` par chaîne (TTL ~3 min) pour éviter le spam Helix.
- **Faits** : `IGDBClient(client_id, client_secret)` calqué sur `TwitchClient` — **même app token
  client_credentials** (IGDB s'authentifie avec l'OAuth Twitch). `POST https://api.igdb.com/v4/games`,
  headers `Client-ID` + `Authorization: Bearer {token}`, corps apicalypse :
  `search "{game_name}"; fields name,platforms.name,genres.name,first_release_date,summary,
   involved_companies.company.name,involved_companies.developer,involved_companies.publisher;
   limit 5;` → prendre le meilleur match (nom le plus proche, cf. matching ci-dessous).
- **Matching Helix→IGDB** à soigner (homonymes/éditions) : normaliser (casse/accents/ponctuation),
  préférer un match exact du nom, sinon le 1er résultat ; si distance trop grande → **pas de faits**.
- **Cache faits** par `game_name` (clé normalisée), TTL long (heures). ⚠️ **Garde-fou** : si IGDB ne
  trouve rien / match douteux → renvoyer `None` (pas de faits inventés).

### 2.B — Détecteur « question sur le jeu » (large, FR + EN)
Dans `game_info.py` `detect_game_question(text) -> str|None` (0 LLM, regex insensible casse/accents,
comme l'anti-injection) : renvoie une **catégorie** (`platform`/`genre`/`studio`/`mode`/`release`/
`about`/`which_game`) ou `None`.
- Exiger un **marqueur interrogatif** (`?` ou tournure « c'est quoi / quel / sur quoi / qui a fait /
  ça sort quand / ça parle de quoi / dispo sur »).
- Mots-clés par catégorie : plateforme (`pc, ps5, xbox, switch, steam, console, dispo sur`), genre
  (`genre, type de jeu, fps, rpg, rogue`), studio/éditeur (`studio, développeur, éditeur, qui a fait,
  developer, publisher`), mode (`solo, multi, coop, multijoueur`), date (`sortie, sort quand, date,
  release`), pitch (`ça parle de quoi, c'est quoi l'histoire, de quoi ça parle`), quel-jeu
  (`c'est quoi ce jeu, quel jeu, what game`).
- **Rester conservateur** : ne pas déclencher sur une phrase random (éviter le sur-déclenchement).

### 2.C — Arbitrage (anti-spam : jamais les 6, cf. [[plan-silence-total-bots]])
- **Bot adressé (nommé)** → c'est lui qui répond. Le chemin *mention* de `dispatch.py` (`trigger_re`,
  l.25) ne se déclenche déjà que pour le bot nommé : si `detect_game_question` matche dans ce chemin,
  on **injecte les faits IGDB** dans le contexte de génération (voir 2.D).
- **Non adressé** → **UN seul bot « co-host » désigné par salon** répond (jamais les autres). Désignation
  **par config, cloisonnée** : ajouter par bot dans `twitch_config.json` une clé `cohost_channels`
  (liste de chaînes, défaut `[]`). Dans le chemin *passif* de `dispatch.py`, ajouter une option
  spontanée « réponse jeu » **gâtée par** : `enable_greetings`/toggle dédié ? → utiliser un nouveau
  flag `game_qa` (2.F) ET `chan in cohost_channels` ET `detect_game_question(text)`. Soumise au
  rate-limit global + un cooldown dédié (ex. 30 s/chaîne) pour éviter le flood.
- Ordre dans le passif : garder « au plus une action spontanée » (var `spontaneous_sent`) — la réponse
  jeu passe **avant** greeting/interjection si elle matche, et pose `spontaneous_sent = True`.

### 2.D — Réponse in-persona ancrée sur les faits
- Construire un **bloc de faits** court (`Plateformes: … | Genre: … | Studio: … | Éditeur: … | Sortie:
  … | Résumé: …`) à partir des faits IGDB (uniquement les champs pertinents à la catégorie détectée).
- Injecter ce bloc dans le prompt de génération existant (`_generate_response`) via une **consigne
  système ponctuelle** : « Voici des FAITS vérifiés sur le jeu en cours : {faits}. Réponds à la question
  du viewer **dans ta personnalité**, en t'appuyant UNIQUEMENT sur ces faits. N'invente rien. Si un fait
  manque, dis-le en restant en personnage. » Le pitch « de quoi ça parle » peut s'appuyer sur `summary`
  (ou rester flavor LLM si `summary` vide).
- **Si pas de faits** (offline/no match) : injecter « Tu n'as pas d'info fiable sur ce jeu → **nuance
  en personnage** (ne donne aucun fait précis). » (garde-fou anti-fait-faux).
- La sortie passe déjà par `send_chat_safe` (filtre ToS + strip didascalies) — rien à ajouter.

### 2.E — Câblage
- `game_info.py` : `IGDBClient`, `get_current_game(chan)`, `get_game_facts(game_name, category)`,
  `detect_game_question(text)`, `format_facts_block(facts, category)`. Caches internes (game par chaîne,
  facts par jeu).
- `shared/twitch/dispatch.py` : appeler `detect_game_question` dans le chemin mention (injecter faits
  avant `_generate_response`) et dans le chemin passif (option co-host gâtée). Instancier l'IGDB/Helix
  client une fois sur le `TwitchChatBot` (réutiliser `self.client_id/secret`).
- **Ne pas bloquer la boucle** : tous les appels réseau IGDB/Helix en `await` (aiohttp), avec timeout
  (10 s) et try/except → sur erreur, se comporter comme « pas de faits » (nuance en persona). Ne jamais
  laisser une exception réseau tuer le WS (cf. [[fix-cascade-bloque-boucle]]).

### 2.F — Dashboard Feature 2
- `twitch_config.json` par bot : `cohost_channels` (défaut `[]`) + toggle `chat.game_qa` (défaut
  `false` au début, activable par bot). Backend `twitch_config.py` : défauts + getters/setters +
  endpoints. Frontend : dans la section Twitch, sélecteur des chaînes co-host + toggle « Répond aux
  questions sur le jeu ». Runtime : lus dans `setup_twitch_chat` (comme les autres toggles l.308-313).

### 2.G — Tests Feature 2
- `test_detect_game_question` : questions plateforme/genre/studio/mode/date/pitch → bonne catégorie ;
  phrase non-question / random → `None` (anti-sur-déclenchement).
- `test_format_facts_block` : faits IGDB → bloc lisible ; champs manquants tolérés.
- `test_igdb_match` : nom Helix ≈ nom IGDB → bon jeu ; nom absurde → pas de faits.
- Arbitrage : mock — bot non désigné (`chan ∉ cohost_channels`) ne répond pas à une question non adressée.

---

## Ce qu'on GARDE / ne casse pas
- Persona complet partout, filtre ToS de sortie (`send_chat_safe`), anti-injection, rate-limits (18/30 s),
  cooldowns, silence entre bots (`TWITCH_PEER_BOTS`), strip didascalies, cloisonnement par bot.
- **Aucune modif Discord.** Aucune modif de la cascade LLM ni des prompts persona (Feature 2 = simple
  injection ponctuelle de faits dans le contexte de génération existant).
- « 0 outil agentique sur Twitch » : IGDB/Helix sont des **lookups de faits internes**, pas des outils
  exposés au LLM ni au viewer.

## Critères d'acceptation
1. `!discord` (et liens configurés au dashboard) répondent avec l'URL, **par bot**, **sans modifier
   aucun bot_*.py** ; une commande lien ne peut pas écraser un built-in (`!decret`…).
2. Sur une chaîne co-host, « c'est sur quelle plateforme ? / qui a fait ce jeu ? / ça parle de quoi ? »
   → le bot répond **en persona** avec des faits IGDB **exacts** (plateforme/genre/studio/mode/date/pitch).
3. Jeu introuvable sur IGDB (ou chaîne offline) → le bot **nuance en personnage**, n'assène **aucun
   fait faux**.
4. **Jamais 6 réponses** : bot nommé → lui ; sinon seul le co-host désigné répond ; rate-limité.
5. Aucune régression : les 6 bots démarrent et chattent ; boucle WS non bloquée par les appels réseau.
6. `py_compile` OK ; `pytest tests/` vert (+ nouveaux tests Features 1 & 2).

## Notes pour Antigravity
- **Nouveaux fichiers** : `shared/twitch/game_info.py`. **Modifs** : `shared/twitch_chat.py`
  (enregistrement link_commands + lecture toggles game_qa/cohost), `shared/twitch/dispatch.py`
  (détection + injection faits + option co-host passive), `dashboard/backend/twitch_config.py` (+ front)
  pour `link_commands`, `cohost_channels`, `chat.game_qa`.
- **Réutiliser** le patron `TwitchClient` (client_credentials) de `shared/twitch_announcer.py` pour Helix
  ET IGDB (même token). Ne PAS créer de nouveaux secrets : les creds Twitch app existent déjà par bot.
- Faire les deux features **incrémentalement** (Feature 1 d'abord, plus simple et 0 réseau ; puis
  Feature 2). Commits séparés.
- Rester **conservateur** sur `detect_game_question` (sur-déclencher = spam) et sur le matching IGDB
  (fait faux = pire que pas de réponse).
- Après exécution : `pytest` + vérifier qu'un bot démarre, qu'un `!lien` marche, et (test live user)
  poser une question jeu sur une chaîne co-host.
