# PLAN — Dashboard « bot-first » + correction du toggle décret mal placé

## Contexte & bug constaté
Le toggle **Décret activé** (`index.html:431-438`, conteneur `#discord-features-container`, codé en dur
`feat-decret-sheogorath`) est **niché dans l'onglet TWITCH « Présence & connexion »** — piloté par
`presence-bot-select` (`app.js:637/667/671`). C'est une fonctionnalité **Discord**, donc mal rangée.
Cause de fond : **côté Discord il n'existe AUCUNE page de config par bot** (Discord = Vue d'ensemble,
Logs, Erreurs, Clés API, Conversations, Rapports = tout en supervision/lecture). Le toggle a donc
atterri dans le seul écran doté d'une config par bot… qui est Twitch.

Décision user (2026-07-02) : réorganiser le dashboard **par bot d'abord**, avec un sélecteur global
« Bot » (dont **Tous**), le contenu en **onglets plateforme Discord | Twitch**, et le mode **Tous** qui
applique une action à chaque bot. Le décret repart côté Discord dans la foulée.

## État actuel (repères)
- **Sidebar** (`index.html:46-61`) : section ▸ DISCORD (overview/logs/errors/api-keys/conversations/
  reports) + section ▸ TWITCH (twitch-presence/twitch-events/twitch-economy/twitch-listen/twitch).
- **Navigation** (`app.js:77-90`) : `.nav-links li[data-target]` → affiche la `.view#<target>`.
- **Fragmentation des sélecteurs de bot** : `twitch-bot-select`, `presence-bot-select`,
  `events-bot-select`, `economy-bot-select`, `listen-bot-select` — un par sous-onglet Twitch.
- **Backend** (`app.py`) : `/api/bots` · `/api/features/{bot_id}` GET/PUT (Discord features) ·
  `/api/twitch` GET · `/api/twitch/all` PUT + `/api/twitch/all/subscriptions` POST (bulk) ·
  `/api/twitch/{bot_id}` (+ /subscriptions, /chat, /rewards, /listen) · supervision (logs/errors/
  api-usage/conversations/reports).
- **Features Discord** (`features_config.py`) : `DEFAULTS = {"decret_enabled": True}`, par bot du
  `BOT_REGISTRY`. **PAS** d'endpoint bulk `all` pour les features. (Jeux/Mémoire du mock = ILLUSTRATIFS,
  pas encore des toggles backend → ne PAS les promettre, juste garder le cadre extensible.)
- **Liste des bots** : source de vérité = `BOT_REGISTRY` (backend) / `BOT_REGISTRY_JS` (front,
  `app.js:289`). ⚠️ Un tableau EN DUR existe (`app.js:192 ["sheogorath","maiq","alfred","onizuka",
  "johnny","malena"]`) — à remplacer par `BOT_REGISTRY_JS`/`/api/bots` pour ne plus dupliquer.

---

## Cible : structure « bot-first »
Séparer clairement **SUPERVISION** (transversale, inchangée) et **CONFIGURATION** (bot-first, neuve).

### Sidebar
```
▸ SUPERVISION            (transversal, tous bots — INCHANGÉ)
   Vue d'ensemble · Logs · Erreurs · Clés API · Conversations · Rapports
▸ CONFIGURATION          (une seule entrée → vue bot-first)
   Configuration des bots
```

### Vue « Configuration des bots » (le cœur du chantier)
```
┌───────────────────────────────────────────────┐
│ Bot : [ ▼ Tous | Sheogorath | Johnny | … ]     │  ← UN sélecteur global (#config-bot-select)
├───────────────────────────────────────────────┤
│ [ Discord ] [ Twitch ]                          │  ← onglets plateforme
│                                                 │
│ === Discord ===                                 │
│   • Décret activé .................... [ON/OFF] │  (Sheo ; extensible aux futures features)
│ === Twitch ===  (sous-onglets ou accordéon)     │
│   Présence · Événements · Habitués/éco ·        │
│   Écoute live · Annonces                        │
└───────────────────────────────────────────────┘
```

## Frontend — travaux
1. **Sélecteur global unique** `#config-bot-select` construit dynamiquement depuis `BOT_REGISTRY_JS`
   (option `Tous` en tête). Il REMPLACE les 5 sélecteurs Twitch (`twitch/presence/events/economy/
   listen-bot-select`) : tous les handlers lisent désormais `#config-bot-select`.
2. **Onglets plateforme** Discord | Twitch dans la vue Configuration (bascule d'affichage simple).
3. **Onglet Discord** : nouveau panneau qui rend les features via `/api/features/{bot_id}` — y **DÉPLACER
   le toggle décret** (retirer `#discord-features-container` de la section Twitch presence). Rendu
   générique : itérer sur les clés du bot (aujourd'hui `decret_enabled`) → 1 checkbox chacune, libellée
   proprement. (Le décret n'a d'effet que pour Sheo : soit ne l'afficher que pour `sheogorath`, soit le
   montrer mais grisé/annoté pour les autres — au choix, mais cohérent.)
4. **Onglet Twitch** : regrouper les 5 écrans Twitch existants sous l'onglet (sous-onglets internes ou
   accordéon), tous pilotés par `#config-bot-select`. Réutiliser le HTML/JS existant, juste re-câbler la
   source du bot.
5. **Mode « Tous »** : quand `#config-bot-select == all`, les actions s'appliquent à tous les bots.
   - Twitch : réutiliser `/api/twitch/all` + `/api/twitch/all/subscriptions` (déjà là).
   - Discord features : appeler le NOUVEAU `/api/features/all` (cf. backend). L'UI en mode Tous montre
     l'action « appliquer à tous » (le libellé des toggles devient une action bulk on/off).
6. Nettoyer le tableau de bots EN DUR (`app.js:192`) → `BOT_REGISTRY_JS`.

## Backend — travaux
1. **`PUT /api/features/all`** (nouveau, miroir de `/api/twitch/all`) : body `{feature, value}` →
   `FeaturesConfigManager.set_feature(bot_id, feature, value)` pour chaque `bot_id` de `BOT_REGISTRY`.
   Valider `feature ∈ DEFAULTS` et `value: bool` (réutiliser la validation existante).
2. Rien d'autre à changer côté données : `bot_features.json` + endpoints par bot restent la source.
   (`decret_enabled` déjà lu par les bots, cf. [[plan-decret-desactivable]] — ne PAS toucher le runtime
   des bots.)

## Ce qu'on GARDE / ne casse pas
- **Supervision** (overview/logs/errors/api/conversations/reports) : inchangée, transversale.
- Endpoints Twitch par bot + bulk `all` existants, `/api/features/{bot_id}`, `bot_features.json`.
- Le runtime des 6 bots (ils lisent `bot_features.json` / `twitch_config.json` au démarrage — aucune
  modif bot). Auth dashboard (mot de passe) inchangée.
- Le nettoyage des rôles de décret côté bot (cf. [[plan-decret-desactivable]]).

## Critères d'acceptation
1. Le toggle **Décret** est dans **Configuration → onglet Discord** (bot = Sheogorath), PLUS dans aucun
   écran Twitch. Il persiste toujours via `/api/features/sheogorath` (décret coupé = plus d'auto ni de
   `!décret`, comportement runtime inchangé).
2. **UN seul** sélecteur de bot pilote toute la vue Configuration (les 5 sélecteurs Twitch ont disparu).
3. Onglets **Discord | Twitch** fonctionnels ; le contenu suit le bot sélectionné.
4. Mode **Tous** : un toggle Discord (via `/api/features/all`) et une action Twitch (via `/api/twitch/
   all`) s'appliquent aux 6 bots en un clic.
5. Supervision inchangée et fonctionnelle. Aucune régression des endpoints existants.
6. Aucun tableau de bots en dur résiduel dans `app.js` (source = `BOT_REGISTRY_JS`).
7. `py_compile` backend OK ; le dashboard se lance (`start_dashboard.bat`) et navigue sans erreur console.

## Notes pour Antigravity
- Fichiers : `dashboard/frontend/index.html`, `dashboard/frontend/js/app.js`, (`css/dashboard.css` au
  besoin), `dashboard/backend/app.py` (1 endpoint `/api/features/all`). Ne PAS toucher le runtime des bots.
- Réutiliser au MAXIMUM le HTML/JS Twitch existant (présence/events/éco/écoute/annonces) : on ne
  réécrit pas leur logique, on remplace juste leur sélecteur de bot par le sélecteur global et on les
  range sous l'onglet Twitch.
- Jeux/Mémoire du mockup = ILLUSTRATIFS : ne pas inventer de toggles sans feature backend. Garder
  l'onglet Discord **générique/extensible** (rendu piloté par les clés de `/api/features/{bot_id}`), de
  sorte qu'ajouter une future feature = l'ajouter à `DEFAULTS` et elle apparaît toute seule.
- Gotcha connu : relancer `start_dashboard.bat` après toute modif backend (cf. [[plan-dashboard-hybride-bots]]).
- Après exécution : lancer le dashboard, vérifier les 7 critères (surtout décret côté Discord + mode Tous).
