# PLAN — Dashboard : correctifs, données réelles, UX & fonctionnalités

## Objectif
Faire passer le dashboard (`dashboard/`) de « belle vitrine » à « outil fiable » :
1. **Phase 1 (bugs)** — corriger ce qui est cassé ou factice (graphiques mock, tuiles mortes,
   route masquée, faux bouton, XSS).
2. **Phase 2 (UX/design)** — toasts au lieu d'`alert()`, CSS consolidé, rendu différentiel,
   assets vendorisés (plus de CDN).
3. **Phase 3 (fonctionnalités)** — uptime + RAM/CPU par bot, santé cascade LLM, rapport réel
   téléchargeable, journal d'audit, résolution d'erreurs persistée.

> Contexte : backend FastAPI (`dashboard/backend/app.py`, port 8501, localhost only, auth
> par cookie de session) + frontend vanilla JS/CSS (`dashboard/frontend/`). Les bots tournent
> sous Docker (services compose = ids du `BOT_REGISTRY` : sheogorath, maiq, alfred, johnny,
> sugar, malena ; conteneurs `bot-<id>`).

---

## ⚠️ POINTS CRITIQUES (à lire avant de commencer)

1. **Ne PAS toucher à l'authentification** (`app.py` lignes ~40-197) : middleware, sessions,
   cookies — c'est audité et conforme. Les nouveaux endpoints héritent automatiquement du
   verrou via le middleware `require_auth` (toute route `/api/*` hors `_PUBLIC_PATHS`).
2. **FastAPI matche les routes dans l'ORDRE DE DÉCLARATION** : toute route statique
   (`/api/xxx/all`) doit être déclarée AVANT sa jumelle paramétrée (`/api/xxx/{bot_id}`).
   C'est précisément le bug 1.1 — ne pas le réintroduire ailleurs.
3. **Échappement HTML systématique** : le frontend injecte via `innerHTML` des données
   d'origine externe (logs contenant des messages Discord, pseudos de viewers Twitch,
   messages custom). TOUT ce qui vient de l'API et finit dans du HTML passe par `escapeHtml()`
   (à créer, § 1.5). Aucune exception.
4. **Gotcha dev local** : après modification d'un fichier de `backend/`, relancer
   `start_dashboard.bat` manuellement (pas de hot-reload). À rappeler dans le rapport final.
5. **Pas de nouvelle dépendance pip** sans nécessité : `psutil` est déjà dans
   `dashboard/backend/requirements.txt` ; les stats Docker passent par `subprocess` + CLI
   `docker`, comme le fait déjà `bot_manager.py`.
6. **Rester en vanilla JS/CSS** — pas de framework, pas de build step. C'est un choix du projet.

---

# PHASE 1 — BUGS (priorité absolue)

## 1.1 Route `/api/features/all` masquée → boutons « Décret sur tous » cassés
**Fichier** : `dashboard/backend/app.py` (lignes ~409-438)

- Actuellement `@app.put("/api/features/{bot_id}")` (l.416) est déclaré AVANT
  `@app.put("/api/features/all")` (l.424). Résultat : `PUT /api/features/all` est capturé
  avec `bot_id="all"` → `ValueError "Bot 'all' non enregistré"` → 400. Les boutons
  « Activer/Désactiver Décret sur tous » du frontend ne fonctionnent pas.
- **Fix** : déplacer la définition de `set_feature_all` (route `/api/features/all`)
  AVANT `set_feature` (route `/api/features/{bot_id}`). Aucun changement de logique.

## 1.2 Graphiques : brancher les VRAIES données (fin des mocks)
**Fichiers** : `dashboard/frontend/js/charts.js` (réécriture quasi complète),
`dashboard/backend/conversation_analyzer.py`, `dashboard/backend/app.py`

Les 3 graphiques affichent des tableaux hardcodés (`[12, 19, 3, 5, 2, 3]`…) ; le fetch réel
est en commentaire. Les endpoints backend existent déjà en partie.

### a) Nouveau backend : activité horaire
- Dans `conversation_analyzer.py`, ajouter une méthode `get_activity(hours=24)` :
  requête sur `interactions` groupée par heure (`strftime('%Y-%m-%dT%H:00', timestamp)`),
  retourne `{"buckets": [{"hour": "...", "count": N}, ...]}` avec les heures vides à 0
  (générer la série complète côté Python pour que la courbe soit continue).
  Gérer `db absente` comme `get_stats` (retour `{"error": ...}`).
- Dans `app.py`, exposer `GET /api/conversations/activity?hours=24`.
  ⚠️ Déclarer cette route AVANT `GET /api/conversations` n'est pas nécessaire (chemins
  distincts), mais la placer à côté pour la lisibilité.

### b) `charts.js` — remplacer les mocks
- `loadActivityChart()` → fetch `/api/conversations/activity?hours=24`, labels = heures
  (format `HH:00`), data = counts. Garder le style actuel (line, fill, tension 0.4).
- `loadApiUsageChart()` → fetch `/api/api-usage?hours=24`, utiliser `by_api`
  (clés = noms d'API, valeurs = `calls`). Doughnut inchangé ; couleurs : garder la palette
  existante, boucler si plus de 4 providers.
- `loadConversationChart()` → fetch `/api/conversations?days=7`, utiliser `by_bot`
  (`{bot_name: {messages: N}}`). Labels = display names via `BOT_REGISTRY_JS` (exposé par
  `app.js`, chargé avant `charts.js`… **attention** : `charts.js` est chargé AVANT `app.js`
  dans `index.html` — soit inverser l'ordre des `<script>`, soit dupliquer un petit map
  local. Préférer : déplacer la déclaration `BOT_REGISTRY_JS` dans `charts.js` (chargé en
  premier) et la retirer d'`app.js` — une seule source).
- Chaque loader : en cas d'erreur/DB vide, afficher un graphique vide + un texte discret
  « Aucune donnée » (plugin title ou placeholder), PAS les données mock.
- Supprimer tout tableau de données hardcodé du fichier.

## 1.3 Tuiles de stats mortes (3 sur 4)
**Fichiers** : `dashboard/frontend/js/app.js`, `dashboard/backend/error_analyzer.py`, `app.py`

`stat-errors`, `stat-api-success`, `stat-users` ne sont jamais mis à jour (seul
`stat-active-bots` l'est, dans `fetchBotsStatus`).

- **Backend** : ajouter à `error_analyzer.py` une méthode `count_recent(hours=24)`
  (COUNT sur `error_events` avec `timestamp > cutoff` et `resolved = 0`). Exposer
  `GET /api/errors/count?hours=24` dans `app.py`.
  ⚠️ ORDRE : déclarer `/api/errors/count` AVANT toute future route `/api/errors/{...}`
  paramétrée (cf. point critique n°2). Actuellement `/api/errors/analyze` est en query
  param, pas de conflit, mais garder le réflexe.
- **Frontend** (`app.js`, dans `refreshAllData()`) :
  - `stat-errors` ← `/api/errors/count?hours=24`.
  - `stat-api-success` ← `/api/api-usage?hours=24` : taux global pondéré =
    `(total appels - total erreurs) / total appels` (sommer `calls` et `errors` de `by_api`) ;
    afficher `—` si 0 appel.
  - `stat-users` ← `/api/conversations?days=7` → `unique_users`.
  - Mutualiser : un seul fetch de `/api/api-usage` et `/api/conversations` partagé entre
    tuiles et graphiques si simple à faire proprement (sinon, fetchs séparés acceptés —
    c'est du localhost).

## 1.4 « Marquer comme résolu » : le rendre réel
**Fichiers** : `dashboard/backend/error_analyzer.py`, `app.py`, `frontend/js/app.js`

- `error_analyzer.py` : méthode `resolve(error_id)` → `UPDATE error_events SET resolved = 1
  WHERE id = ?` ; retourner `{"success": bool}`.
- `app.py` : `POST /api/errors/{error_id}/resolve`.
- `app.js` (`showErrorDetail`) : remplacer `onclick="alert('Résolu!')"` par un appel réel
  qui, en cas de succès : toast de confirmation (§ 2.1), rechargement de la liste
  (`loadErrors()`), vidage du panneau détail.
- `loadErrors()` : ne charger par défaut que les erreurs NON résolues
  (`/api/errors?resolved=false`) + petit toggle « Voir résolues » au-dessus de la liste.

## 1.5 XSS : échappement HTML systématique
**Fichier principal** : `dashboard/frontend/js/app.js`

- Créer en tête de fichier :
  ```js
  function escapeHtml(s) {
      return String(s ?? '').replace(/[&<>"']/g, c =>
          ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  ```
- L'appliquer sur TOUTES les interpolations de données API dans du HTML, notamment :
  - `appendLogLine` : `log.message`, `log.bot`, `log.level` ;
  - `renderTwitchBotView` : `sub.twitch_login`, `sub.discord_channel_id`, `sub.custom_message` ;
  - `loadTwitchEconomy` : `entry.name` (pseudos de viewers = données hostiles) ;
  - `renderRewardsTable` : `title`, `action` ;
  - `addLinkRow` : `cmd`, `url`, `label`, `message`, `aliasesStr` (⚠️ ce sont des `value="..."`
    d'inputs : échapper est indispensable pour ne pas casser l'attribut) ;
  - `loadErrors` / `showErrorDetail` : `err.bot_name`, `err.error_type`, `data.auto_diagnosis`,
    `data.suggested_fix`, `data.category` ;
  - `loadApiKeysStatus` : `k.api_key_display`, `k.last_error`.
- `renderRewardsTable` : le `onclick="deleteRewardMapping('${title...}')"` avec échappement
  manuel de quotes est fragile → remplacer par `data-title` + `addEventListener` (ou
  `encodeURIComponent` dans l'attribut et `decodeURIComponent` à la lecture).

## 1.6 Robustesse `actionAllBots`
**Fichier** : `dashboard/frontend/js/app.js` (l.~417)

- `data.error.includes(...)` crashe si `data.error` est `undefined` → garder :
  `(data.error || '').includes(...)`.
- Remplacer le `alert()` final par un toast (§ 2.1).

---

# PHASE 2 — UX / DESIGN

## 2.1 Système de toasts + confirmations (fin des `alert()`/`confirm()`)
**Fichiers** : `dashboard/frontend/js/app.js`, `frontend/css/dashboard.css`, `frontend/index.html`

- Créer un mini-système (vanilla, ~60 lignes JS + CSS) :
  - `toast(message, type)` avec `type ∈ {success, error, info}` : conteneur fixe en bas à
    droite (`#toast-container` ajouté au `<body>`), disparition auto après 4 s, animation
    d'entrée/sortie douce, couleurs = variables CSS existantes (`--success`, `--danger`,
    `--info`). Empilable.
  - `confirmDialog(message)` → `Promise<boolean>` : petit modal glass centré avec boutons
    « Confirmer » (danger) / « Annuler », fermeture Échap = annuler.
- Remplacer TOUTES les occurrences (~25) :
  - `alert(succès)` → `toast(..., 'success')` ;
  - `alert(erreur)` → `toast(..., 'error')` ;
  - `confirm(...)` → `await confirmDialog(...)` (fonctions concernées : `setTwitchEnabledAll`,
    `deleteTwitchSubscription`, + toute suppression).
- `grep -n "alert(\|confirm(" dashboard/frontend/js/*.js` doit retourner 0 occurrence à la fin.

## 2.2 Consolidation CSS (fin des styles inline)
**Fichiers** : `dashboard/frontend/index.html`, `frontend/css/dashboard.css`, `frontend/js/app.js`

- Déplacer le bloc `<style>` embarqué dans la section `#bot-config` d'`index.html`
  (règles `.tabs-platforms`, `.twitch-subtabs`, `.placeholder-text`) vers `dashboard.css`.
- Créer des classes utilitaires dans `dashboard.css` et remplacer les `style="..."` répétitifs
  d'`index.html` ET des templates JS :
  - `.form-input` (le pattern `padding:10px; border-radius:8px; background:#111520;
    border:1px solid var(--border-glass); color:#fff` revient ~15 fois) ;
  - `.form-textarea` (idem + resize) ;
  - `.card-section` (le pattern `padding:1.5rem; margin-bottom:1.5rem` des `.twitch-card`) ;
  - `.hint-text` (le pattern `font-size:0.85em; opacity:0.6/0.7`) ;
  - `.section-note` (le « ⚠️ Les changements s'appliquent au redémarrage du bot. »).
- Objectif raisonnable : plus AUCUN `style=` multi-propriétés dans les chaînes HTML générées
  par `app.js` ; dans `index.html`, tolérer quelques `style` one-shot (display:none initiaux)
  mais éliminer les blocs de 5+ propriétés.
- **Ne pas changer le rendu visuel** : c'est un refactor iso-design (vérif visuelle avant/après).

## 2.3 Rendu différentiel de la grille des bots (anti-flicker)
**Fichier** : `dashboard/frontend/js/app.js` (`renderBotsGrid`)

- Aujourd'hui : `innerHTML = ''` + reconstruction toutes les 30 s → l'animation `slideIn`
  rejoue en boucle et la grille clignote.
- **Fix** : construire chaque carte avec un `id="bot-card-<id>"` une seule fois ; aux refreshs
  suivants, si la carte existe déjà, ne mettre à jour QUE : badge statut (classe + texte),
  uptime, et le bloc boutons (start vs restart/stop) — uniquement si `status` a changé
  (mémoriser le dernier statut par bot dans un objet).
- L'animation d'entrée ne doit jouer qu'au premier rendu.

## 2.4 Vendoriser les assets (plus de CDN)
**Fichiers** : `dashboard/frontend/index.html`, nouveau dossier `dashboard/frontend/vendor/`

- Télécharger et servir localement :
  - `chart.umd.min.js` (Chart.js v4) → `vendor/chart.umd.min.js` ;
  - Font Awesome : récupérer le CSS + les webfonts (woff2) → `vendor/fontawesome/`
    (adapter les chemins `url(...)` du CSS vers `./webfonts/`) ;
  - Polices Inter (400/500/600/700) et JetBrains Mono (400/500) en woff2 →
    `vendor/fonts/` + un `vendor/fonts.css` avec les `@font-face`.
- Mettre à jour les `<link>`/`<script>` d'`index.html` vers `/static/vendor/...`.
- Vérif : `grep -n "cdn\|googleapis\|cloudflare" dashboard/frontend/index.html` → 0 résultat ;
  le dashboard doit s'afficher correctement réseau coupé.

---

# PHASE 3 — FONCTIONNALITÉS

## 3.1 Uptime réel + RAM/CPU par bot
**Fichiers** : `dashboard/backend/bot_manager.py`, `frontend/js/app.js`, `frontend/css/dashboard.css`

- `bot_manager.get_status()` retourne actuellement `uptime: 0` en dur.
- **Uptime** : `docker inspect -f '{{.State.StartedAt}}' bot-<id>` → parser l'ISO 8601
  (attention aux nanosecondes Docker : tronquer à la microseconde avant `fromisoformat`),
  `uptime = now - started_at` en secondes.
- **RAM/CPU** : UN SEUL appel groupé pour les 6 bots (pas 6 subprocess) :
  `docker stats --no-stream --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"` dans
  `get_all_status()`, parser et distribuer aux bots concernés. Champs ajoutés au payload :
  `cpu_percent` (float) et `mem_mb` (float), `null` si bot arrêté ou stats indisponibles.
  ⚠️ `docker stats --no-stream` prend ~2 s : le faire dans un
  `asyncio.to_thread`/executor côté endpoint OU accepter la latence (endpoint appelé
  toutes les 30 s seulement — acceptable). Ne PAS bloquer les autres routes : passer
  `list_bots` en `def` (FastAPI l'exécute déjà dans un threadpool si non-async) — vérifier
  que c'est le cas, sinon `asyncio.to_thread`.
- **Frontend** (`renderBotsGrid` / mise à jour différentielle) : sous l'uptime, une ligne
  discrète `🧠 128 Mo · ⚙️ 2.4%` quand le bot tourne. Style via classe CSS (pas d'inline).

## 3.2 Panneau « Santé cascade LLM » (section Clés API)
**Fichiers** : `dashboard/frontend/index.html` (section `#api-keys`), `frontend/js/app.js`

- Les données existent déjà : `GET /api/api-usage` (`by_api` : calls/errors/success_rate)
  et `GET /api/api-usage/keys` (statut par clé : active/cooldown/dead, last_error).
- Ajouter en HAUT de la section API une rangée de cartes provider (une par `api_name`
  présent dans `by_api`, généré dynamiquement) : nom, nb appels 24h, taux de succès
  (vert ≥ 95 %, orange ≥ 80 %, rouge sinon), nb de clés actives / total (croisement avec
  `/api/api-usage/keys` sur le préfixe `api_name`), dernière erreur (tronquée, title au survol).
- But : voir en un coup d'œil quel provider de la cascade est mort (cf. épisodes Grok/Gemini).
- Pas de nouveau backend nécessaire.

## 3.3 Rapport réel + téléchargement/copie
**Fichiers** : `dashboard/backend/report_generator.py`, `app.py`, `frontend/js/app.js`,
`frontend/index.html`

- `report_generator.generate()` est un STUB (« Ceci est un rapport généré automatiquement... »).
  L'implémenter réellement en composant du Markdown à partir des modules existants
  (les instancier/recevoir en paramètres — suivre le câblage dans `app.py`) :
  - **scope `all`** : statut des 6 bots (via `BotManager.get_all_status()`), compte
    d'erreurs non résolues (via `ErrorAnalyzer`), usage API par provider (via
    `APITracker.get_usage(hours)`), stats conversations (via `ConversationAnalyzer`),
    liste des clés mortes/en cooldown ;
  - **scope `errors`** : les 20 dernières erreurs (bot, type, message, sévérité, timestamp) ;
  - **scope `api`** : usage détaillé + état de chaque clé.
  - Conserver l'en-tête « Instruction pour IA » en fin de rapport (c'est le but du feature :
    copier-coller dans un LLM).
  - ⚠️ `ReportGenerator.__init__` ne reçoit que `db_path` : passer les autres managers via
    le constructeur dans `app.py` (injection simple), pas d'imports croisés.
- **Frontend** : le résultat contient déjà `content`. Après génération, au lieu du `alert()` :
  afficher le rapport dans un panneau sous le formulaire (`<pre>` scrollable, échappé !)
  avec 2 boutons : « 📋 Copier » (`navigator.clipboard.writeText(content)` + toast) et
  « ⬇️ Télécharger » (Blob + `URL.createObjectURL` + `<a download="filename">` — pas besoin
  d'endpoint de download).

## 3.4 Journal d'audit des actions dashboard
**Fichiers** : `dashboard/backend/app.py` (+ nouveau `dashboard/backend/audit_log.py`),
`frontend/index.html`, `frontend/js/app.js`

- Nouveau module `audit_log.py` : classe `AuditLog(db_path)` sur `data/api_usage.db` — NON,
  utiliser une table dédiée `dashboard_audit` dans `data/bots_database.db` :
  `(id INTEGER PK, timestamp TEXT DEFAULT datetime('now'), action TEXT, target TEXT,
  detail TEXT)`. `CREATE TABLE IF NOT EXISTS` à l'init. Méthodes : `log(action, target,
  detail="")` et `get_recent(limit=100)`.
- Dans `app.py`, appeler `audit.log(...)` dans : start/stop/restart bot (avec le résultat
  succès/échec), toutes les mutations de config (`PUT/POST/DELETE /api/twitch/*`,
  `PUT /api/features/*`), génération de rapport. PAS sur les lectures ni le login (le
  mot de passe ne doit jamais approcher ce log).
- Endpoint `GET /api/audit?limit=100`.
- **Frontend** : nouvelle entrée sidebar « Journal d'audit » (section SUPERVISION, icône
  `fa-clock-rotate-left`) → vue simple : tableau (heure, action, cible, détail), 100 dernières
  entrées, bouton actualiser. Données échappées (§ 1.5).

---

# ORDRE D'EXÉCUTION & COMMITS

1 commit par bloc cohérent, messages en français, préfixe `fix(dashboard):` ou
`feat(dashboard):` / `refactor(dashboard):` :

1. `fix(dashboard): route /api/features/all déclarée avant la route paramétrée` (§ 1.1)
2. `fix(dashboard): graphiques et tuiles branchés sur les vraies données` (§ 1.2 + 1.3)
3. `fix(dashboard): résolution d'erreurs persistée + garde actionAllBots` (§ 1.4 + 1.6)
4. `fix(dashboard): échappement HTML systématique des données API` (§ 1.5)
5. `feat(dashboard): toasts et confirmations non bloquantes` (§ 2.1)
6. `refactor(dashboard): consolidation CSS, fin des styles inline` (§ 2.2)
7. `fix(dashboard): rendu différentiel de la grille des bots` (§ 2.3)
8. `feat(dashboard): assets vendorisés, plus de CDN` (§ 2.4)
9. `feat(dashboard): uptime réel + RAM/CPU par bot` (§ 3.1)
10. `feat(dashboard): panneau santé cascade LLM` (§ 3.2)
11. `feat(dashboard): rapports réels avec copie/téléchargement` (§ 3.3)
12. `feat(dashboard): journal d'audit des actions` (§ 3.4)

---

# CRITÈRES DE VÉRIFICATION (avant de conclure)

- [ ] `python -m py_compile` sur tous les `.py` modifiés de `dashboard/backend/`.
- [ ] `PUT /api/features/all` retourne 200 (tester via curl avec session, ou vérifier
      l'ordre des décorateurs).
- [ ] `grep -n "\[12, 19, 3\|\[300, 50\|150, 80, 45" dashboard/frontend/js/charts.js` → 0
      (plus aucune donnée mock).
- [ ] `grep -n "alert(\|confirm(" dashboard/frontend/js/*.js` → 0.
- [ ] `grep -n "cdn\|googleapis\|cloudflare" dashboard/frontend/index.html` → 0.
- [ ] `grep -c "escapeHtml" dashboard/frontend/js/app.js` → présent sur tous les points § 1.5.
- [ ] Lancement local (`start_dashboard.bat`) : login OK, les 7 vues s'affichent sans erreur
      console, graphiques rendus (même vides si DB vide), pas de flicker de la grille à 30 s.
- [ ] Test manuel : marquer une erreur résolue → disparaît de la liste ; générer un rapport
      → contenu réel affiché + copie + téléchargement OK ; une action start/stop apparaît
      dans le journal d'audit.
- [ ] Rendu visuel inchangé après § 2.2 (comparaison avant/après).

## Hors périmètre (ne PAS faire)
- Responsive/mobile (repoussé).
- Toute modification de l'authentification, du bind réseau, du CORS.
- Nouveau framework front ou build step.
- Modification du code des bots eux-mêmes (`shared/`, `Sheogorath/`, etc.) — ce plan est
  100 % contenu dans `dashboard/`.
