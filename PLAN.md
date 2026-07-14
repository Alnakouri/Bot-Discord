# PLAN — Dashboard UX pass : garde-fous + feedback honnête + cohérence visuelle

> Antigravity exécute. Claude a rédigé (2026-07-14).
> Cibles : `dashboard/frontend/js/app.js`, `dashboard/frontend/index.html`,
> `dashboard/frontend/css/dashboard.css`. AUCUN changement backend.
> Repérer par CONTENU (noms de fonctions, textes cités), pas par numéro de ligne figé.

## Contexte

Audit ergonomie/design 2026-07-14. Le socle est bon (design system cohérent, bot-first,
toasts, re-render différentiel). Trois problèmes :
1. **Aucune confirmation sur les actions destructives bots** — alors que `confirmDialog`
   (Promise, overlay stylé) EXISTE déjà dans `app.js` (~l.34, CSS `confirm-overlay`/`confirm-box`
   présents) et n'est utilisée QUE pour 2 actions Twitch (bulk enable/disable, suppression
   d'abonnement). « Arrêter Tous les Bots » = 1 clic sans filet.
2. **Feedback mensonger après sauvegarde** : les configs Twitch ne s'appliquent qu'au
   redémarrage du bot (note en `opacity:0.6` sous les boutons), mais le toast de succès dit
   « enregistré avec succès ! » → l'utilisateur croit que c'est actif.
3. **Incohérences visuelles** : 3 fonds d'input différents (`#161a24`, `#111520`, `#0b0d14`)
   pour le même rôle, ~200 styles inline, 2 restes de renommage.

## Phase A — Câbler `confirmDialog` sur les actions destructives

Dans `app.js` :

1. `actionAllBots(action)` : en tête de fonction, AVANT toute mutation UI :
   ```js
   if (action === 'stop' && !await confirmDialog("Arrêter TOUS les bots ? Ils seront déconnectés de Discord et Twitch.")) return;
   if (action === 'restart' && !await confirmDialog("Redémarrer TOUS les bots ? Coupure brève sur Discord et Twitch.")) return;
   ```
   (`start` reste sans confirmation : action non destructive.)
2. `botAction(botId, action)` : confirmation UNIQUEMENT pour `stop` :
   ```js
   if (action === 'stop' && !await confirmDialog(`Arrêter le bot « ${botId} » ?`)) return;
   ```
   (`restart` individuel reste direct : opération courante, relance automatique.)
3. `setDiscordFeatureAll('decret_enabled', false)` — la fonction générique
   `setDiscordFeatureAll(feature, value)` : si `value === false`, demander
   `confirmDialog("Désactiver cette fonctionnalité sur TOUS les bots ?")`.

⚠️ `botAction` est appelée depuis du HTML généré (`onclick="botAction(...)"`) : elle doit
rester sur `window.` et devenir/rester `async` (elle l'est déjà).

## Phase B — Toast « redémarrage requis » avec action

1. Nouvelle helper dans `app.js`, à côté de `window.toast` (même mécanique DOM/classes) :
   ```js
   window.toastAction = function(message, actionLabel, onAction, type = 'success') { ... }
   ```
   - Même rendu que `toast` + un `<button class="btn btn-primary btn-sm">` à droite.
   - Durée d'affichage 10 s (au lieu de 4) ; clic sur l'action → callback + fermeture.
   - Le message passe par `escapeHtml` (comme `toast`) ; le bouton est construit en DOM
     (`createElement` + `addEventListener`), PAS en innerHTML avec le label interpolé.
2. Remplacer le toast de succès des saves Twitch qui exigent un redémarrage —
   `savePresenceSettings`, `saveChatChannels`, `saveCohostChannels`, `saveLinkCommands`,
   `saveRewardsMapping`, `saveListenSettings` (toutes lisent `config-bot-select`) — par :
   ```js
   toastAction("Enregistré — sera appliqué au redémarrage du bot.",
               "Redémarrer maintenant", () => botAction(botId, 'restart'));
   ```
   (le `botId` est déjà une variable locale dans chacune de ces fonctions).
3. `saveTwitchBotSettings` (annonces) : si le polling des annonces est relu à chaud par
   l'announcer, garder le toast simple ; sinon même traitement. En cas de doute (ne pas
   fouiller le backend) : même traitement `toastAction`, c'est sans danger.
4. Dans `index.html`, raccourcir les 5+ notes répétées
   « ⚠️ Les changements s'appliquent au redémarrage du bot. » → les GARDER mais en une
   forme brève « ⚠️ Appliqué au redémarrage du bot. » (l'info principale vit désormais
   dans le toast).

## Phase C — Harmoniser les inputs (un seul fond, des classes)

1. `dashboard.css` : ajouter un token `--input-bg: #111520;` dans `:root` et étendre les
   classes existantes :
   - `.form-input` (existe déjà) : s'assurer qu'elle couvre `background: var(--input-bg)`,
     bordure `var(--border-glass)`, couleur, padding, radius.
   - Créer `.form-select` et `.form-textarea` sur le même socle (le `<textarea>` garde
     `resize: vertical`).
   - Ajouter un état focus commun : `.form-input:focus, .form-select:focus,
     .form-textarea:focus { border-color: var(--accent); outline: none; }` (le focus
     `.form-input:focus` existe déjà — l'étendre aux 3).
2. `index.html` : remplacer les styles inline des `input/select/textarea` de la section
   `bot-config` (fonds `#161a24`, `#111520`, `#0b0d14`) par ces classes. NE PAS chercher
   à éliminer TOUS les styles inline du fichier (hors périmètre) : SEULEMENT les champs
   de formulaire, qui sont l'incohérence visible.
3. Le champ mot de passe du login (`#login-password`, fond `#161a24` inline) : passer sur
   `.form-input` aussi.

## Phase D — Restes de renommage (2 fixes)

1. `index.html`, filtre logs : `<option value="johnny">Johnny Silverbot</option>` →
   `Johnny Silverhand`.
2. `dashboard.css` : `--onizuka: #0ea5e9;` → `--sugar: #0ea5e9;` + mettre à jour toute
   utilisation (`grep -rn "onizuka" dashboard/frontend/` doit finir à 0 ; vérifier aussi
   `app.js` et `charts.js` au cas où la couleur est référencée côté JS).

## Phase E (optionnelle, si le reste est vert) — Focus clavier + statut système réel

1. Focus visible global : `button:focus-visible, li[data-target]:focus-visible {
   outline: 2px solid var(--accent); outline-offset: 2px; }`.
2. « Système Normal » (bas de sidebar) : refléter l'état réel déjà connu du front —
   dans la boucle de refresh (`refreshAllData`/`renderBotsGrid`), si au moins un bot
   attendu est `stopped` → pastille orange + « X/6 bots actifs » ; si tous up → vert
   « Système Normal ». Pas de nouvel appel API : réutiliser les données du polling existant.

## Garde-fous

- AUCUN changement backend (`dashboard/backend/`) : chantier 100 % front.
- Ne pas toucher à la logique de polling/WebSocket logs, ni au re-render différentiel des
  cartes bots (il est bon).
- `confirmDialog` existante : ne pas la réécrire, juste l'UTILISER.
- Tester à la main après (pas de suite front automatisée) : `start_dashboard.bat`, puis
  vérifier : (1) « Arrêter tous » → modale ; Annuler → rien ne se passe ; (2) sauvegarde
  d'une config Twitch → toast avec bouton « Redémarrer maintenant » fonctionnel ;
  (3) les inputs de bot-config ont tous le même fond ; (4) plus aucun « onizuka » ni
  « Silverbot » dans le front. GOTCHA connu : relancer `start_dashboard.bat` après modif
  backend — ici front only, un refresh navigateur (Ctrl+F5, cache) suffit.
- Suite pytest : rien à casser (front pur), mais lancer `python -m pytest tests/ -q` par
  acquit (210 verts attendus).
