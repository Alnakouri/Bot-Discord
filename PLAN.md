# PLAN — Dashboard v2, Lot 2 : les gabarits de rendu

Rédaction : Claude, le **2026-09-09**. Exécution : **Antigravity**.
Suite du Lot 1 (la peau), livré et relu le même jour.

---

## Où on en est

Le Lot 1 est dans l'**arbre de travail**, pas commité : `index.html`,
`css/dashboard.css`, `js/app.js`, `js/charts.js`. Il a apporté la palette de la maquette
aux bons rôles (page `#0a0a14`, rail `#0e0e1a`, panneau `#12121f` **opaque**, bloc
imbriqué `#161628`, bordure `#23233a`, survol `#43436b`), retiré le verre dépoli des
panneaux, câblé la pastille de glyphe des bots, et rebranché `/api/bots` comme autorité
sur le nom et la couleur.

Ce qu'il reste, et qui est l'objet de ce lot : **le balisage produit par `app.js`**.

---

## Les règles n'ont pas changé

1. **Le backend ne change pas.** Aucune route ajoutée, renommée ou supprimée. Aucun
   changement de schéma SQLite. Ce que la maquette montre et qu'aucune route ne sert est
   **retiré de la vue** et listé dans le rapport — jamais inventé, jamais laissé en dur.
2. **Pas de React, pas d'étape de build**, pas de `npm`/`pnpm`, pas de CDN. JS vanille.
3. **Tout reste hors-ligne** : aucun `https://` chargé dans la page.
4. **Aucune fonction ne disparaît.** La liste de survie du Lot 1 vaut encore : connexion et
   verrou fail-closed, confirmations destructives, toast de redémarrage, bouton
   `/api/dashboard/restart`, mode test global et par bot, les 3 interrupteurs par bot dont
   `repartee_lessons_enabled`, le flux WebSocket `/api/logs/stream`, les 5 onglets Twitch.
5. **Ne pas toucher à** `backend/` **ni aux tests.**

---

## Ce que ce lot fait, exactement

`app.js` charge des données puis **fabrique des chaînes HTML**. Ce lot ne change **que ces
chaînes**. Ne bougent pas : les `fetch` et leurs routes, les `id` que le code va chercher,
les gestionnaires `onclick`, l'ordre des appels, la navigation (`data-target`,
`.view.active`).

Référence visuelle : **`dashboard/design_v2/template_pretty.html`** — c'est le seul endroit
où le balisage de la maquette est lisible. `maquette_source.jsx` ne contient que les
données et les calculs de couleur.

---

## Ce que le backend sert vraiment — à lire AVANT de coder

C'est ce tableau qui décide de ce qui est portable. Mesuré le 09/09 sur les routes.

| Vue | La maquette montre | Servi ? |
|---|---|---|
| overview | 4 tuiles KPI | oui (`stat-active-bots`, `stat-errors`, `stat-api-success`, `stat-users`) |
| overview | barre de progression sous la tuile | **2 sur 4 seulement** : bots actifs (n/6) et taux de succès (%). Erreurs 24 h et utilisateurs 7 j n'ont pas de dénominateur — **pas de barre** sur ces deux-là |
| overview | bandeau « 2 bots hors ligne · 1 erreur critique » | oui, **calculable côté client** depuis `/api/bots` + `/api/errors` — aucune route à ajouter |
| overview | `msgs` par bot sur la carte, statut `degraded` | **non** — `/api/bots` ne les sert pas. À retirer |
| logs | horodatage, bot, niveau, message | oui |
| errors | catégorie, diagnostic, correction | oui (`POST /api/errors/analyze`) |
| errors | occurrences 24 h, fichier source, 3 lignes de trace | **à vérifier dans `context`** : `analyze` renvoie un champ `context` (JSON). Regarder ce qu'il contient réellement avant de décider. S'il est vide, ces trois blocs sautent |
| api-keys | groupement **par bot**, fournisseur, nom du slot d'environnement, % de consommation | **non, et c'est structurel** : `api_key_status` a pour clé primaire `(api_name, key_index)` — **aucune colonne bot**. Le suivi des clés est global aux 6 bots. Grouper **par fournisseur**, et le dire dans le rapport |
| api-keys | statut, appels, erreurs, dernier usage, dernière erreur | oui |
| conversations | volume par bot | oui (`by_bot`) |
| conversations | « Top interlocuteurs » | **non** — `get_stats` ne renvoie aucune liste d'utilisateurs. À retirer |
| reports | périmètre, fenêtre, aperçu, télécharger | oui |
| audit-logs | date, opérateur, action, bot, détails | oui |
| bot-config | les 5 onglets Twitch | oui |

---

## Fonction par fonction

Ordre conseillé : du plus simple au plus risqué. **Une fonction, une passe, on relit.**

1. **`showLogin` (`app.js:140`)** — la maquette ne dessine pas l'écran de connexion. Lui
   donner la D.A. : panneau `--bg-card` opaque, bordure `--border-glass`, bouton accent. Le
   formulaire, ses `id` et le verrou fail-closed ne bougent pas.
2. **`updateStatTiles` (`app.js:464`) + les 4 tuiles d'`index.html`** — gabarit maquette :
   libellé en petites capitales `#7c8699` + icône teintée, valeur 27 px en gras teintée,
   unité, barre 4 px, ligne d'explication. Voir plus haut : la barre ne vaut que pour 2
   tuiles sur 4.
3. **Le bandeau d'alerte de l'overview** — nouveau bloc, calculé depuis les données déjà
   chargées. Dégradé rouge horizontal, bordure `#4a2230`, bouton « Voir l'erreur » qui
   bascule sur la vue `errors` par le mécanisme de navigation **existant**.
4. **`appendLogLine` (`app.js:754`)** — rangée : heure `#7c8699` (62 px — la maquette dit
   `#5f6880`, qui échoue au contraste, voir plus bas), nom du bot coloré
   (92 px, ellipse), pastille de niveau (74 px, fond teinté), message. Bordure gauche 2 px
   à la couleur du niveau. ⚠️ Cette fonction est appelée **par le WebSocket, ligne à
   ligne** : garder `insertAdjacentHTML`, ne pas reconstruire la liste à chaque message.
5. **`loadErrors` + `showErrorDetail` (`app.js:786` et `820`)** — liste à gauche en boutons
   (fond teinté par sévérité, bordure `#43436b` au survol), détail à droite en blocs
   `#161628` : catégorie, diagnostic, correction. Le bouton « Marquer comme résolu » reste
   câblé sur `resolveError(id)`.
6. **`loadAuditLogs` (`app.js:931`)** — tableau : en-tête sur fond de panneau, lignes
   séparées par `#1c1c2f`, action en pastille, bot en pastille colorée, détails en gris.
7. **`generateReport` (`app.js:969`)** — pastilles de périmètre et de fenêtre, bouton accent
   pleine largeur, aperçu en `JetBrains Mono` sur `#0c0c16`. Ne pas toucher au
   téléchargement ni au presse-papiers.
8. **`loadApiKeysStatus` (`app.js:870`)** — le plus gros écart : la maquette groupe par bot,
   le backend ne le permet pas. **Grouper par fournisseur** (`api_name`), une carte
   `#0f0f1c` par fournisseur, une ligne par clé : pastille d'état, fournisseur en pastille,
   identifiant en `code` violet `#c4b5fd`, badge de statut, compteurs à droite, barre de
   consommation, dernière erreur. La barre n'a de sens que rapportée au total des appels du
   fournisseur — si ce calcul n'est pas honnête, pas de barre.
9. **Les 5 vues Twitch** (`renderTwitchBotView:1041`, `loadTwitchPresence:1229`,
   `loadTwitchEvents:1445`, `renderRewardsTable:1457`, `loadTwitchEconomy:1532`,
   `loadTwitchListen:1572`) — mêmes panneaux, mêmes tableaux, mêmes pastilles que le reste.
   ⚠️ C'est là que vivent le plus de gestionnaires et d'`id` d'ancrage : les recopier un par
   un, et cliquer chaque onglet après.

---

## Là où on AMÉLIORE la maquette au lieu de la copier

La maquette est une image d'un dashboard en bonne santé. Le vrai dashboard passe une partie
de sa vie à charger, à n'avoir rien à montrer, ou à échouer. Ces sept points sont des
écarts **voulus** : ils ne tombent pas sous la règle 1, ils la complètent.

1. **Les trois états que la maquette ne dessine nulle part.** Elle n'a que des données en
   dur : **zéro** écran de chargement, **zéro** état vide, **zéro** état d'erreur. Le
   dashboard actuel en a 12 (`placeholder-text`), 3 (`loader`) et 5 (« Erreur de
   chargement »). Chaque gabarit porté **garde ses trois états**, habillés à la D.A. Un
   panneau vide doit dire *pourquoi* il est vide — « aucune clé configurée » et « base
   illisible » ne sont pas le même écran, et `get_keys_status` renvoie `[]` dans les deux
   cas.
2. **Une couleur de la maquette échoue au contraste.** `#5f6880` (l'heure des lignes de
   log, 12,5 px) donne **3,34 : 1** sur le panneau `#12121f` — le minimum lisible est
   4,5 : 1. Utiliser `#7c8699` (5,06 : 1). Les autres tiennent : `#7c8699` 5,06,
   `#8f99ad` 6,47, `#c3cbd9` 11,4, `#f2f4f8` 16,9. Mesuré, pas estimé.
3. **Ne pas porter `all:unset` sur les boutons.** La maquette l'écrit sur chacun ; il
   supprime aussi le **focus clavier**, et ce dashboard se pilote au clavier quand on a les
   mains dans un `docker logs`. Garder les classes `.btn` existantes, n'emprunter que les
   couleurs, rayons et espacements.
4. **Garder les tailles de texte en `rem`.** La maquette est en px fixes (11,5 / 12,5 /
   13,5). En px, la page cesse de répondre au zoom du navigateur.
5. **L'écran de connexion.** La maquette a un bouton « Écran de connexion » qui n'ouvre
   rien : le vrai écran est à dessiner, pas à transposer.
6. **Les toasts et les boîtes de confirmation** ne sont pas dessinés non plus. Ils restent
   tels quels côté comportement et prennent la D.A. — ce sont eux qui protègent les actions
   destructives.
7. **La pastille d'état sur l'avatar.** La maquette pose un point coloré en bas à droite du
   glyphe. Le CSS actuel a déjà `.bot-card.running::after` — une règle **morte** : la classe
   `running` n'est jamais ajoutée. Soit on la ravive, soit on la remplace par le point de la
   maquette, mais **pas les deux** ; et l'état doit être mis à jour dans la branche « carte
   déjà présente » de `renderBotsGrid`, sinon il ment dès le premier changement d'état.

---

## Les pièges de ce dépôt, qui s'appliquent tous ici

- **`escapeHtml` n'est pas décoratif.** Toute donnée d'API qui entre dans une chaîne HTML y
  passe. Un audit précédent a déjà corrigé un XSS dans ce fichier.
- **`escapeHtml` ne protège pas un attribut `style`.** Une couleur venue de l'API passe par
  `safeColor()` (ajouté au Lot 1) : seul un `#RRGGBB` est accepté.
- **Ne rien supprimer par motif textuel.** Filtrer des lignes parce qu'elles citent un mot a
  déjà cassé la syntaxe de 11 fichiers et effacé des fixtures dans ce dépôt.
- **Un `id` retiré du HTML ne casse aucun test** — il casse la page, en silence. Après
  chaque fonction, vérifier que tous les `getElementById` du bloc touché trouvent encore
  leur cible.
- **`pyflakes` AVANT `pytest`.**
- **Un seul `pytest` à la fois** : la suite se bind le port 8599 et partage `data/` avec
  l'hôte. Deux suites en parallèle font échouer `test_dashboard_restart` sans raison.
- **`node --check dashboard/frontend/js/app.js`** avant de dire que c'est fini : une
  interpolation mal fermée dans un gabarit ne se voit nulle part ailleurs.

---

## Comment livrer

1. **Ne pas commiter, ne pas pousser, ne pas créer de branche.** Laisser dans l'arbre de
   travail ; la relecture commite.
2. **Livrer par groupes de 2 ou 3 fonctions**, dans l'ordre ci-dessus, en s'arrêtant entre
   chaque. Les 14 fonctions d'un coup rendent la relecture impossible.
3. **Rendre compte de ce qui n'a pas été fait**, nommément : chaque chose que la maquette
   montre et qui a été retirée faute de route pour la servir.

## Recette

- `pyflakes`, puis `pytest` (seul), puis `node --check` sur les deux fichiers JS.
- Lancer le dashboard **par le raccourci du Bureau**, pas à la main.
- Parcourir les 8 vues et la liste de survie, clic par clic.
- Ne pas dire « c'est bon » avant que la **CI soit verte**.

---

# ANNEXE — rapport de livraison du Lot 1 (09/09)

Antigravity avait livré une passe de palette ; la relecture l'a reprise.

**Corrigé à la relecture :** les quatre fonds étaient mal affectés (`#12121f`, couleur des
**panneaux**, avait été posée sur le **fond de page**) ; le verre dépoli est retiré des deux
règles `.glass` et des 15 surfaces translucides écrites en dur dans `index.html` ; `glyph`
et `textColor`, copiés de la maquette et lus nulle part, servent désormais la pastille
d'identité des bots ; la grille des bots relit `/api/bots` au lieu de l'objet en dur du
frontend (la dérive était déjà là : backend « 🔫 Johnny Silver**bot** », copie
« Silver**hand** ») ; `safeColor()` ferme le passage d'une couleur d'API dans un attribut
`style`, où `escapeHtml` ne protège rien.

**Non fait au Lot 1, et c'est l'objet de ce plan :** le balisage des 8 vues. Non porté faute
de route : `msgs` par bot, statut `degraded`, `pct` par clé. Non joué : le parcours au clic,
qui demande le mot de passe du dashboard.

**Reste à trancher :** les fichiers dérivés de la maquette ne sont pas suivis.
`design_v2/extract.py` (reproductible, à garder) et `template_pretty.html` (209 Ko, la
référence de ce lot) méritent le dépôt ; `template_extracted.json` (215 Ko) en est la source
brute, dont `template_pretty.html` est déjà le rendu.
