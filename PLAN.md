# PLAN — Présence permanente de Sheogorath dans le chat Twitch (industrialisation)

> **Objectif** : transformer le prototype jetable `twitch_test.py` en un module
> propre, intégré au process du bot, avec **connexion permanente** (auto-refresh
> du token) et **reconnexion automatique**. **Sheo = pilote**, mais le module est
> écrit **générique** pour brancher les 5 autres bots ensuite sans réécriture.
>
> Décisions validées (user, 2026-06-22) :
> 1. **Intégré au process du bot** (module `shared/twitch_chat.py`, démarré comme
>    l'announcer). Pas de service séparé.
> 2. **Auto-refresh** du token (refresh_token + client_id/secret), persistance
>    chiffrée/locale, regénération avant expiration.
> 3. **Sheo pilote**, module shared généralisé (persona + clés par bot).
>
> Conventions respectées : indépendance des bots (`try/except ImportError` +
> fallback no-op), env chiffré (`shared.secure_env`), réutilisation de
> `shared.llm_cascade.generate_response` + `bot_profiles` (routage par bot),
> données runtime gitignorées.

---

## 0. État de départ (déjà acquis)

- Prototype `twitch_test.py` **fonctionnel** : Sheo se connecte au chat IRC
  (websocket), parse les `PRIVMSG` (préfixe de tags géré), génère une réponse en
  personnage via la cascade LLM et répond. Sert de **référence** ; sera **supprimé**
  en fin de tâche (jetable, gitignoré).
- Bug clé résolu dans le proto : la capability `twitch.tv/tags` préfixe chaque
  ligne par `@tags ` → la regex de parsing doit accepter `(?:@\S+ )?` avant `:`.
- Compte bot Twitch dédié : `compte_bot_sheo`. App Twitch (client_id/secret)
  = celle déjà utilisée par l'announcer (compte perso, OK). User token + refresh
  token obtenus via `twitch token -u -s "chat:read chat:edit"`.

---

## 1. Nouveau module — `shared/twitch_chat.py` (générique)

Patron : même esprit que `shared/twitch_announcer.py` (factory `setup_…` +
classe). Aucune dépendance à un bot précis.

### 1.1 Classe `TwitchChatBot`
Paramètres (tous optionnels sauf bot_id/logger), **alignés sur l'announcer** :
`bot_id`, `logger`, `username`, `channels: list[str]`, `client_id`, `client_secret`,
`personality_prompt`, `key_manager`, `mistral_client`, `groq_client`,
`openrouter_client`, `bot_label`.

Responsabilités :
- **Connexion IRC websocket** (`wss://irc-ws.chat.twitch.tv:443`), CAP
  `twitch.tv/tags twitch.tv/commands`, `PASS oauth:<token>`, `NICK`, `JOIN` (une
  ou plusieurs chaînes).
- **Boucle de réception** robuste : gestion `PING/PONG`, parsing `PRIVMSG`
  (regex avec préfixe de tags optionnel), anti-boucle (`author == username` →
  ignore ; ignore aussi les autres comptes de bot connus si une liste est fournie).
- **Déclencheur** : mention `@<username>` ou nom du perso dans le message
  (paramétrable ; pour Sheo : `sheo`, `sheogorath`, `@compte_bot_sheo`).
- **Génération** : `shared.llm_cascade.generate_response(...)` avec
  `system_prompt = personality_prompt`, `bot_label`, `max_tokens≈120`,
  `temperature≈0.9`. Réponse aplatie sur **une ligne**, tronquée à **480 car.**
  (limite chat = 500).
- **Mémoire de conversation courte** (pilote) : par `(channel, user)`, un
  `deque(maxlen=6)` en RAM (3 derniers échanges) passé en `conversation_history`.
  *(Mémoire long terme partagée = hors périmètre, note §7.)*
- **Anti-spam / rate limit** : cooldown par utilisateur (~3 s) + limiteur global
  (≤ ~18 msgs / 30 s, marge sous la limite Twitch de 20) pour ne jamais se faire
  couper par Twitch.

### 1.2 Auto-refresh & connexion permanente — `TwitchAuth`
Petit helper dédié (dans le même fichier) :
- **Stockage** : `DATA_DIR/twitch_chat_auth_<bot_id>.json` (écriture **atomique**
  tmp + `os.replace`), schéma `{access_token, refresh_token, expires_at}`.
  Au **1er** démarrage, si le fichier n'existe pas, on **amorce** depuis l'env
  (`TWITCH_OAUTH_TOKEN` + `TWITCH_REFRESH_TOKEN`).
- **Validation** au démarrage : `GET https://id.twitch.tv/oauth2/validate`
  (header `Authorization: OAuth <token>`) → récupère `expires_in`. Si invalide
  ou expiration < marge → refresh.
- **Refresh** : `POST https://id.twitch.tv/oauth2/token`
  `grant_type=refresh_token&refresh_token=…&client_id=…&client_secret=…`
  → nouveau `access_token` **et** `refresh_token` (Twitch fait tourner le refresh
  token : on **persiste les deux**). Met à jour `expires_at`.
- **Refresh proactif** : tâche périodique (~toutes les 60 min, ou quand
  `expires_at - now < 30 min`) qui renouvelle avant expiration.
- **Refresh réactif** : sur `:tmi.twitch.tv NOTICE … Login authentication failed`
  ou fermeture websocket → refresh puis reconnexion.

### 1.3 Boucle de vie / reconnexion automatique
- `run()` = boucle `while not self._stopped:` : (re)connecte, écoute ; sur
  déconnexion/erreur → **backoff exponentiel** (1, 2, 4, … plafonné à 60 s) puis
  reconnecte. C'est ce qui assure le **24/7**.
- Démarrée comme **tâche asyncio** (pas une `tasks.loop`, car c'est un consommateur
  websocket long-vécu), conservée pour pouvoir l'annuler proprement à l'arrêt.

### 1.4 Factory `setup_twitch_chat(...)`
Comme `setup_twitch_announcer` : retourne `None` (et loggue) si les crédentiels
manquent (`username`, token amorçable, `client_id/secret`, `channels`). Sinon
instancie `TwitchChatBot`. **Aucune exception ne doit remonter** au bot.

---

## 2. Câblage dans `Sheogorath/bot_sheogorath.py`

Strictement calqué sur l'announcer :

- **Import** (vers la ligne 122) :
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
- **Démarrage dans `on_ready`** (à côté du bloc announcer, ~ligne 540) :
  ```python
  global twitch_chat, twitch_chat_task
  if TWITCH_CHAT_AVAILABLE and twitch_chat is None:
      twitch_chat = setup_twitch_chat(
          "sheogorath", logger,
          personality_prompt=sheo_data.PERSONALITY_BASE, key_manager=key_manager,
          mistral_client=mistral_client, groq_client=groq_client,
          openrouter_client=openrouter_client, bot_label="Sheogorath")
      if twitch_chat:
          twitch_chat_task = asyncio.create_task(twitch_chat.run())
  ```
- **Arrêt propre** : dans le handler de fermeture (ou `on_disconnect`/close),
  `if twitch_chat: twitch_chat.stop()` + annuler `twitch_chat_task`. (Best-effort.)
- ⚠️ Le module chat est **autonome** du client Discord : il n'utilise PAS
  `bot.get_channel`, juste sa propre connexion IRC. Donc aucune dépendance forte.

---

## 3. Configuration / secrets

- **Env chiffré de Sheo** (via `shared.secure_env`) — ajouter :
  - `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` (déjà présents pour l'announcer →
    réutilisés).
  - `TWITCH_BOT_USERNAME` = `compte_bot_sheo`
  - `TWITCH_OAUTH_TOKEN` + `TWITCH_REFRESH_TOKEN` (amorçage initial uniquement ;
    ensuite la source de vérité = le JSON persistant en §1.2).
  - `TWITCH_CHAT_CHANNELS` = liste de chaînes à rejoindre (CSV), p. ex.
    `chaine_du_dev`.
- **`.gitignore`** : ajouter `twitch_chat_auth_*.json` (donnée runtime, comme
  `sheo_punishments.json`). *(`twitch_test.env` déjà ignoré + sera supprimé.)*

---

## 4. Nettoyage du jetable

- Supprimer `twitch_test.py` (référence absorbée par `shared/twitch_chat.py`).
- Supprimer `twitch_test.env` (remplacé par l'env chiffré + JSON persistant).
- Retirer la trace `RAW> …` de debug (n'existait que dans le proto).

---

## 5. Vérifications (avant test live)

- `python -m py_compile shared/twitch_chat.py Sheogorath/bot_sheogorath.py` → OK.
- Module **importable seul** (indépendance) : `from shared.twitch_chat import setup_twitch_chat`.
- `setup_twitch_chat` renvoie `None` proprement si un crédentiel manque (pas d'exception).
- Regex `PRIVMSG` accepte le préfixe de tags (`@…`), gère 1+ chaînes.
- Écriture atomique du JSON d'auth vérifiée (tmp + `os.replace`).

## 6. Recette de test (live)

1. Lancer Sheo (process complet, pas le proto) → log « connecté au chat de #… ».
2. Écrire `sheo coucou` depuis un autre compte → Sheo répond en personnage.
3. **Forcer l'expiration** : mettre un `access_token` bidon dans le JSON d'auth +
   relancer → le module doit **refresh via le refresh_token** et se connecter
   quand même (vérifie la persistance du nouveau refresh token).
4. **Couper le réseau** quelques secondes → reconnexion auto (backoff) au retour.
5. Laisser tourner > 4 h → toujours connecté (refresh proactif a joué).

## 7. Hors périmètre (itérations suivantes)

- **Généralisation aux 5 autres bots** : créer un compte Twitch + token par bot,
  câbler `setup_twitch_chat` dans chaque `bot_*.py` (le module est déjà générique).
- **Mémoire long terme partagée** dans le chat Twitch (réutiliser le système
  `shared/` mémoire des bots) — ici on se limite à un contexte court en RAM.
- **Config via dashboard** (activer/désactiver, liste de chaînes, message) comme
  l'announcer — pour l'instant tout est en env.
- **Commandes de chat** (`!…`), modération, réactions aux events (raids, subs).
- Intégration Docker/compose dédiée si on veut isoler la conso.
