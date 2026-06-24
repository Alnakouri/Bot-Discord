# PLAN — Sheo sur Twitch : présence vivante (événements + interjections + commandes + accueil)

> **Contexte** : `shared/twitch_chat.py` gère la présence permanente de Sheo (réponse sur
> mention, anti-injection, profil autonome quotidien — commité e970880). On enrichit Sheo
> pour qu'il se comporte comme un **vrai co-host de stream**. 4 ajouts, tous **génériques**
> (Sheo = pilote, paramètres optionnels off par défaut → les autres bots en hériteront).
>
> **Périmètre validé par l'utilisateur** : 1 (événements), 2 (interjections), 3 (commandes),
> 4 (accueil). **Hors périmètre pour l'instant** : annonces de live Discord (feature 5).

> **PRINCIPE TRANSVERSAL — anti-saturation (exigence forte de l'utilisateur)**
> Tout message **spontané** de Sheo (événements, interjections, accueil) **doit** :
> 1. passer par le **plafond global existant** `global_msg_timestamps` (18 msg / 30 s) —
>    on l'incrémente AVANT chaque envoi spontané, comme pour le chat ;
> 2. respecter en plus un **cooldown propre à chaque feature** (voir ci-dessous).
> Conséquence : même pendant un raid de 300 personnes, le total reste borné, on ne sature
> ni la clé LLM ni la limite d'envoi Twitch (~20 msg/30 s pour un compte non-modérateur).
> Les **commandes (3)** sont quasi sans coût LLM (scriptées/locales).

---

## 0. Pré-requis technique commun : parser les tags IRC

La connexion demande déjà `CAP REQ :twitch.tv/tags twitch.tv/commands` → on reçoit les
**tags** (`@key=val;key=val ...`) sur les lignes `PRIVMSG` et `USERNOTICE`.

Ajouter un helper `_parse_tags(line) -> dict` (split `;` puis `=`, unescape `\s`→espace,
`\:`→`;`, etc.). Servira aux features 1 (events + bits) et 4 (badges habitués).

---

## 1. Réagir aux événements de la chaîne — `shared/twitch_chat.py`

### 1.1 Source des événements
Dans `_connect_and_loop`, en plus de `PRIVMSG_RE`, traiter :
- **`USERNOTICE`** (subs, resubs, dons de subs, raids…). Le tag clé est **`msg-id`** :
  - `sub`, `resub` → `display-name`, `msg-param-cumulative-months`, `msg-param-sub-plan`.
  - `subgift`, `anonsubgift` → `display-name` (offreur) + `msg-param-recipient-display-name`.
  - `submysterygift` → don groupé : réagir **une seule fois** au résumé
    (`msg-param-mass-gift-count`) et **ignorer** les `subgift` enfants qui suivent.
  - `raid` → `msg-param-displayName` + `msg-param-viewerCount`.
  - Le tag **`system-msg`** donne déjà un résumé lisible → idéal à passer au LLM.
- **Cheers / bits** : ce sont des `PRIVMSG` **avec un tag `bits`** → si `bits` présent,
  traiter comme un événement « don de bits » (montant = valeur du tag).

### 1.2 Génération de la réaction
- Méthode `async _react_to_event(chan, kind, ctx: dict) -> str | None`.
- Construit une consigne courte (« {auteur} vient de {sub/raid/bits…} : {détails} ») +
  prompt système persona (`system_prompt_provider()` sinon `personality_prompt`) +
  `ANTI_INJECTION_GUARD`. Appelle la **même cascade** (`generate_response`, `max_tokens≈80`).
- Repli scripté si LLM indisponible/vide (petite liste de réactions en personnage par type).

### 1.3 Garde-fous spécifiques
- **Cooldown événement** : min ~8 s entre deux réactions d'événement (`self._last_event_ts`).
- **Anti-rafale** : un seul message par `submysterygift` (pas un par sub offert) ; un seul
  par `raid`.
- Incrémente `global_msg_timestamps` avant l'envoi (principe transversal). Si plafond
  atteint → on log et on **n'envoie pas** (l'événement passe à la trappe, pas de file).

### 1.4 Activation
- Param `enable_events: bool = False` sur `setup_twitch_chat`. Sheo le passe à `True`.

---

## 2. Interjections spontanées — `shared/twitch_chat.py`

### 2.1 Contexte de chat
- Ajouter un **tampon roulant par salon** `self.channel_recent[chan] = deque(maxlen=8)`
  (chaque message non-bot, sous forme « auteur: texte ») mis à jour à chaque `PRIVMSG`.

### 2.2 Déclenchement
Sur un `PRIVMSG` qui **ne** déclenche **pas** (pas de mention, pas de commande) :
- Tirage aléatoire `random.random() < interjection_chance` (défaut **0.03**), **ET**
- `now - self._last_interjection > interjection_min_interval` (défaut **600 s**), **ET**
- budget global non saturé.
→ Génère une réplique courte (`_generate_interjection`) basée sur `channel_recent[chan]`,
  prompt persona + guard, cascade `max_tokens≈70`. Met à jour `self._last_interjection` et
  `global_msg_timestamps`.

### 2.3 Activation / réglages
- Params : `enable_interjections=False`, `interjection_chance=0.03`,
  `interjection_min_interval=600`. Sheo active avec des valeurs prudentes.

---

## 3. Commandes de chat — `shared/twitch_chat.py` (générique) + adaptateurs Sheo

### 3.1 Dispatch générique
- Param `commands: dict[str, callable] | None = None`. Clé = nom sans `!` (ex. `"decret"`),
  valeur = callable `(author: str, args: str) -> str | Awaitable[str]`.
- Dans le handler de message, **avant** le test de mention : si `text` commence par `!`,
  extraire `cmd` + `args`, et si `cmd ∈ self.commands` → exécuter (await si coroutine),
  envoyer la chaîne retournée, **stop** (ne pas aussi déclencher une réponse mention).
- **Cooldown commande** : réutiliser le cooldown par utilisateur (3 s) + un cooldown global
  léger par commande pour éviter le spam d'une même commande.
- Alias : accepter une table d'alias (ex. `decree`→`decret`).

### 3.2 Adaptateurs Sheo (`Sheogorath/`)
- **`!faveur`** → réutiliser `FaveurSystem`, mais **cloisonné Twitch** : nouveau fichier
  `data/sheo_faveurs_twitch.json` (ou clés préfixées `tw:`) — **ne pas mélanger** avec les
  identités Discord. Retourne le rang/points du `author` Twitch.
- **`!décret`** → **nouveau générateur texte seul** (pas de rôle, pas d'image) : recycler le
  prompt LLM de décret (≈ `bot_sheogorath.py` l.779) en version **texte court**, cible =
  l'auteur de la commande ; repli sur les templates de décret existants. ~1 appel LLM,
  initié par le viewer, compté dans le budget.
- **`!fromage`** → `minigames.jeu_fromage(<hash de l'author>)` → mise en forme texte.
- **`!sheo`** / **`!folie`** → listes statiques de répliques en personnage (0 LLM).
- Sheo construit le dict `commands={"decret":…, "faveur":…, "fromage":…, "sheo":…,
  "folie":…}` (+ alias) et le passe à `setup_twitch_chat`.

---

## 4. Accueil des arrivants / habitués — `shared/twitch_chat.py`

### 4.1 État persistant par viewer
- Fichier `data/twitch_viewers_{bot_id}.json` :
  `{ "<login>": { "count": 7, "last_seen": "2026-06-23" } }` (gitignoré).
- Lecture au démarrage, écriture best-effort (debounce : sauver au plus une fois / 30 s).

### 4.2 Détection « premier message de la session »
- Set RAM `self.session_seen` (par login). Au **1er message** d'un login dans la session :
  - incrémenter `count`, mettre `last_seen` = aujourd'hui, marquer vu pour la session ;
  - produire un **accueil** (voir 4.3) ;
  - (Twitch ne notifie pas l'arrivée de façon fiable sans EventSub → on se base sur le
    1er message, c'est suffisant et sans scope supplémentaire.)

### 4.3 Message d'accueil — **templaté par défaut (0 LLM)**
- Pool de salutations en personnage, formaté avec `@login` ; variante « habitué » si
  `count >= seuil` (ex. ≥ 5) qui mentionne le nombre de visites.
- *(Option `greeting_use_llm=False` par défaut — on garde les templates pour éviter tout
  coût et tout risque de flood lors d'un raid ; activable plus tard.)*

### 4.4 Anti-flood (crucial pendant un raid)
- **Cap d'accueil** : au plus 1 accueil / ~15 s (`self._last_greet_ts`), et on **saute**
  l'accueil si le budget global est déjà bien entamé. Mieux vaut rater un bonjour que
  noyer le chat. Incrémente `global_msg_timestamps`.

### 4.5 Activation
- Param `enable_greetings: bool = False`. Sheo → `True`.

---

## 5. Ordre de traitement d'un message (handler) — précédence claire
Pour un `PRIVMSG` (après filtres auteur=self / bots connus / cooldown user) :
1. **Commande** (`!…` connue) → exécuter, **stop**.
2. **Mention** (`trigger_re`) → réponse LLM existante, **stop**.
3. Sinon (message « passif ») : mettre à jour `channel_recent` + faveur passive éventuelle,
   puis **au plus UNE** sortie spontanée : **accueil** (si 1er message session) **sinon**
   **interjection** (probabiliste). Jamais les deux sur le même message.
Les `USERNOTICE`/bits (feature 1) sont une **branche séparée** traitée avant `PRIVMSG_RE`.

---

## 6. Vérifications (avant test live)
- `python -m py_compile shared/twitch_chat.py Sheogorath/bot_sheogorath.py` → OK.
- `_parse_tags` testé sur des exemples réels de `USERNOTICE`/`PRIVMSG` (unescape correct).
- Simuler les lignes IRC (sub, resub, subgift, submysterygift, raid, cheer) → 1 seule
  réaction par événement, jamais de rafale ; cooldown respecté.
- Commandes : dispatch OK, alias OK, inconnue ignorée, cooldown actif ; `!faveur` écrit
  bien dans le fichier **Twitch** (pas Discord).
- Accueil : 1 seul par login/session, variante habitué au-delà du seuil, **cap anti-flood**
  vérifié sur une rafale simulée.
- **Anti-saturation** : un flot massif (events + mentions + accueils) ne dépasse jamais
  18 envois / 30 s (logs `🚨 rate limit`).
- Module toujours importable seul ; toutes les features **off par défaut** ; aucun crash si
  cascade/clé indisponibles (replis).

## 7. Recette de test (live)
1. Faire un sub/cheer (ou simuler) → Sheo réagit **en personnage**, une fois.
2. Simuler un raid → un seul message d'accueil collectif.
3. `!décret`, `!faveur`, `!fromage`, `!sheo` → réponses correctes ; `!faveur` cumule les
   points sur Twitch indépendamment de Discord.
4. Laisser tourner : une **interjection** finit par sortir (rare), pas de spam.
5. Nouveau pseudo qui parle → accueil ; il revient au stream suivant → variante « habitué ».
6. Spammer mentions + commandes : cooldowns + plafond tiennent, pas de saturation de clé.

## 8. Hors périmètre (itérations suivantes)
- Annonces de live Discord (feature 5, `plan-twitch-announce`) — repoussée par l'utilisateur.
- Détection d'arrivée temps réel via EventSub (follows en direct) — le 1er message suffit.
- Modération/timeout (pas de scope, par design).
- Généralisation des 4 features aux 5 autres bots (le module reste générique).
