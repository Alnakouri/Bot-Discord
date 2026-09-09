# PLAN — Dashboard v2 : porter la maquette sur le vrai backend

Rédaction : Claude, le **2026-09-09**, à partir de `Dashboard v2 - autonome.html` fourni par
l'utilisateur (fait avec Claude Design). Remplace le plan de la Phase 3 répartie, **livré,
poussé et déployé** le 08/09 (`d341fcd`, puis `83f05a7`, `2659fdc`, `1639fa1`).

Exécution : **Antigravity**. ⚠️ Relire ce qu'il livre avant de commiter, et commencer par
`pyflakes`, pas par `pytest`.

---

## Ce que le chantier veut obtenir, en une phrase

Le dashboard actuel prend la **direction artistique** de la maquette, **sans qu'une seule
route du backend ne bouge** et sans qu'aucune fonction existante ne se perde en route.

---

## Le point de départ, vérifié

La maquette est dans `dashboard/design_v2/` (voir son `README.md`). Elle a été dépaquetée :
c'est un bundle Claude Design de 1,6 Mo dont seuls 28 Ko sont du code de page
(`maquette_source.jsx`).

**C'est une maquette, pas un dashboard.** Mesuré : **zéro** `fetch` / `XMLHttpRequest` /
`WebSocket`, **zéro** chaîne `/api/`. Toutes les données sont des constantes en dur
(`STATE`, `ERRORS`, `KEYS`, `LOGS`, `AUDIT`, `REPORT`, `FEATURES`, `TWITCH_PANELS`, `SUBS`,
`TOP_USERS`, `LEVELS`). Faire pointer le raccourci du Bureau dessus donnerait une page
morte. Il n'y a donc rien à « brancher » : il y a une peau à transposer.

**La bonne nouvelle, et elle décide de toute la méthode** : les 8 vues de la maquette
portent **exactement les mêmes identifiants** que les 8 vues actuelles —
`overview`, `logs`, `errors`, `api-keys`, `conversations`, `reports`, `audit-logs`,
`bot-config`. Le mécanisme de navigation existant (`data-target` + `.view.active`,
`initNavigation` dans `app.js`) est donc **conservé tel quel**. Et les 3 interrupteurs de
`FEATURES` dans la maquette sont exactement les 3 clés de `features_config.DEFAULTS`
(`decret_enabled`, `repartee_lessons_enabled`, `test_mode`).

C'est un **reskin**, section par section. Les 48 routes de `backend/app.py` ne bougent pas.

---

## Règles qui gouvernent tout le lot

1. **Le backend ne change pas.** Aucune route ajoutée, renommée ou supprimée. Si une vue de
   la maquette montre une donnée qu'aucune route ne sert, elle est **retirée de la vue** —
   on ne fabrique pas d'endpoint pour faire joli. Lister ces cas dans le rapport de
   livraison plutôt que de les inventer.
2. **Pas de React, pas d'étape de build.** La maquette est en React parce que Claude Design
   l'est. Le dashboard est en JS vanille, servi en statique par FastAPI, et doit le rester :
   pas de `npm`/`pnpm`, pas de bundler, pas de CDN. On transpose le **rendu**, pas la
   techno.
3. **Tout reste hors-ligne.** Les fontes et Font Awesome de la maquette doivent être
   vendorisées dans `dashboard/frontend/vendor/` (qui contient déjà `css`, `fonts`, `js`,
   `webfonts`). Aucun `https://` dans `index.html`.
4. **Aucune fonction ne disparaît.** Voir la liste de survie plus bas : elle a été payée
   cher, et une refonte visuelle est exactement le moment où ces choses s'évaporent.

---

## Lot 1 — la peau

**Fichiers** : `dashboard/frontend/index.html`, `dashboard/frontend/css/dashboard.css`.

- Reprendre de `maquette_source.jsx` les **tokens** de la D.A. : fonds (`#12121f`,
  `#141426`, bordures `#23233a`), accent violet, couleurs de sévérité, et la couleur +
  le glyphe **par bot** (`REG` en tête du fichier).
- ⚠️ **La couleur par bot ne doit pas devenir une 7ᵉ copie.** `BOT_REGISTRY`
  (`backend/bot_manager.py`) est déjà l'autorité sur les 6 bots. Soit la couleur/le glyphe
  y sont ajoutés et servis par `/api/bots`, soit ils vivent dans **un seul** objet en tête
  d'`app.js`. Jamais les deux.
- Refaire le balisage des 8 vues. **Conserver** : les `id` de vue, les `data-target`, les
  classes `.view` / `.active`, et tous les `id` d'ancrage que `app.js` va chercher
  (`overview`, `keys-table`, `audit-logs-table`, `report-preview-text`,
  `twitch-links-table-body`, `twitch-rewards-table-body`,
  `economy-leaderboard-table`, `twitch-bot-status-title`…). Le plus sûr est de partir de
  l'`index.html` actuel et de le **rhabiller**, pas de repartir de la maquette.

## Lot 2 — les gabarits de rendu

**Fichier** : `dashboard/frontend/js/app.js` (~75 Ko). La logique ne change pas ; ce sont
les chaînes HTML produites qui changent.

Fonctions à reprendre, une par une : `renderBotsGrid`, `updateStatTiles`, `appendLogLine`,
`loadErrors` + `showErrorDetail`, `loadApiKeysStatus`, `generateReport`, `loadAuditLogs`,
`renderTwitchBotView`, `loadTwitchPresence`, `loadTwitchEvents`, `renderRewardsTable`,
`loadTwitchEconomy`, `loadTwitchListen`, et **`showLogin`** — l'écran de connexion fait
partie du produit et la maquette ne le dessine pas : lui donner la même D.A.

⚠️ `escapeHtml` existe et sert à quelque chose. Toute donnée venant de l'API qui entre dans
une chaîne HTML passe par lui — un audit précédent a déjà corrigé un XSS ici.

---

## La liste de survie — ce qui doit encore marcher après

À vérifier une par une, en cliquant, avant de dire que c'est fini :

- **La connexion** et le verrou fail-closed sur `/api/*` (hors login/health).
- **Les confirmations destructives** et le **toast de redémarrage** (`plan-dashboard-ux-pass`).
- **Le bouton de redémarrage du dashboard** (`/api/dashboard/restart`) : il relance le
  processus depuis `_LANCEMENT_CWD` / `_LANCEMENT_ARGV`, figés au démarrage — n'y toucher
  sous aucun prétexte.
- **Le mode test**, global et par bot, et le sélecteur de serveur privé. Il est **désarmé**
  aujourd'hui ; il doit pouvoir l'être encore.
- **Les 3 interrupteurs par bot**, dont `repartee_lessons_enabled`, ajouté le 08/09.
- **Le flux de logs en WebSocket** (`/api/logs/stream`), pas seulement le `GET /api/logs`.
- **Les 5 onglets Twitch** de `bot-config` : présence, événements/rewards, habitués/éco,
  écoute live, annonces.
- **Les graphiques** (`charts.js`) : la maquette embarque Chart.js 4.4.1 ; vérifier la
  version déjà vendorisée dans `vendor/js` avant d'en ajouter une seconde.

---

## Le raccourci du Bureau : rien à faire

Vérifié le 09/09 : `~/Desktop/Dashboard Bots Discord.lnk` pointe sur
`dashboard\start_dashboard.bat`, working dir `dashboard\`, icône `shell32.dll,21` — c'est
**exactement** ce que produit `dashboard/create_shortcut.bat`. Le raccourci lance le
serveur, qui sert `frontend/` : il continuera de servir la v2 sans être modifié.

Il n'y a de raccourci à refaire **que si** l'un de ces trois change : le nom du `.bat`, le
chemin du dépôt, ou l'icône voulue. Dans ce cas, modifier `create_shortcut.bat` **et** le
relancer — les deux, sinon le `.lnk` du Bureau et le script divergent en silence.

---

## Recette

- `pyflakes` puis `pytest` (900 verts avant de commencer ; ⚠️ jamais deux `pytest` en
  parallèle, ils partagent `data/` et le port 8599).
- Lancer le dashboard **par le raccourci du Bureau**, pas à la main : c'est le chemin réel.
- Parcourir les 8 vues et la liste de survie ci-dessus, clic par clic.
- ⚠️ Ne pas dire « c'est bon » avant que la **CI soit verte** : le local ment sur tout ce
  qui dépend de l'environnement.
