# PLAN — Dashboard v2, Lot 3 : les 5 vues Twitch

Rédaction : Claude, le **2026-09-10**. Exécution : **Antigravity**.
Fait suite au Lot 2, livré par Antigravity et **repris à la relecture** le même jour.

---

# ANNEXE D'ABORD — rapport de relecture du Lot 2 (10/09)

À lire avant d'écrire une ligne du Lot 3 : ce sont les mêmes pièges.

## Ce qui était cassé, et qui l'était en silence

**La page ne se chargeait pas du tout.** `app.js` ne passait pas `node --check` — trois
ruptures de syntaxe, dont une seule visible à la fois puisque l'analyseur s'arrête à la
première :

1. une accolade fermante en trop après `loadApiKeysStatus` (ligne 1017) ;
2. une accolade fermante en trop dans `loadAuditLogs` (ligne 1056) ;
3. `updateOverviewAlertBanner` : les **accents graves** des deux gabarits avaient disparu —
   `parts.push(${window.globalOfflineBotsCount} bot hors ligne)` n'est pas du JavaScript.

Un fichier JS qui ne parse pas ne lève rien de visible : le navigateur **n'exécute rien**,
et le dashboard reste un squelette HTML muet. Aucun test ne le voit. La recette du Lot 2
disait `node --check` **avant** de dire que c'est fini ; elle n'a pas été jouée.

## Ce que le mécanisme d'exécution a caché

Le portage a été appliqué par **9 scripts Python jetables** déposés dans
`dashboard/frontend/` (`update_*.py`). Deux conséquences :

- `update_twitch.py` imprime `Success` **sans condition**, alors que 2 de ses 3 expressions
  régulières n'ont **rien** remplacé. La sortie disait que les vues Twitch étaient portées ;
  le diff dit qu'une seule ligne de tableau l'a été. C'est le même défaut que
  [[gotcha-import-ajoute-mais-pas-cable]] : la sortie confirme le **nom** de l'opération,
  pas son **effet**.
- ces scripts étaient posés dans le répertoire **servi en statique** par le dashboard, avec
  des chemins absolus `I:\IA\...` en dur. Déplacés hors du dépôt à la relecture. Un fichier
  `.env.example.md` **vide** traînait aussi à la racine : parti avec.

## Les cinq défauts de fond corrigés à la relecture

1. **Deux barres de progression qui mentaient.** `stat-bar-bots` et `stat-bar-api` ont été
   ajoutées à `index.html` et **jamais** mises à jour par le JS : la barre des bots restait
   à `0 %` pendant que la valeur affichait « 5 / 6 », celle de l'API à `100 %` quoi qu'il
   arrive. Câblées dans `fetchBotsStatus` et `updateStatTiles` ; sans appel du tout, la
   barre API affiche **0 %**, pas 100 %.
2. **L'ancienne règle CSS de l'icône écrasait la nouvelle tuile.** `.stat-card i` posait
   `font-size: 2rem`, un fond violet et `padding: 1rem` — le gros médaillon de la v1, qui
   s'appliquait toujours à la petite icône de tête du gabarit v2. Récrite. `.stat-card h3`,
   `.stat-card p` et `.stat-card.warning/.success i` ne visaient plus aucun élément :
   retirées.
3. **Le bloc `context` du détail d'erreur devinait ses clés.** Le plan disait de **regarder
   ce que `context` contient vraiment**. Il n'a pas été regardé : le code cherchait
   `occurrences_24h`, `source_file`, `trace`. Mesuré en base sur les 10 lignes existantes,
   `context_json` contient `{module, funcName, lineno}` — le `LogRecord` de Python. Les
   trois blocs n'auraient **jamais** rien affiché. Remplacés par un bloc « Origine »
   (`module.fonction:ligne`), qui est ce qui existe.
4. **`document.querySelector('.keys-table-container')`** : cette classe porte **deux**
   éléments dans `index.html` — les clés API et le journal d'audit. Le rendu ne tombait dans
   le bon panneau que parce que celui des clés vient en premier dans le fichier. Ancré sur
   un `id` dédié, `keys-panel`, et l'ancien `<table>` mort (`keys-status-body`) est remplacé
   par son état de chargement.
5. **Le bandeau d'alerte disait « 1 erreur critique »** pour un compteur qui est celui de
   **toutes** les erreurs sur 24 h, et sans accord au pluriel. Corrigé en
   « N erreur(s) sur 24 h ».

Deux détails de la même passe : les quatre valeurs de tuile étaient en `27px` fixes alors
que le plan demandait des `rem` (la page cessait de répondre au zoom) ; et `${time}` /
`${timeStr}`, seules interpolations non échappées des nouveaux gabarits, passent maintenant
par `escapeHtml`.

## Ce que ce lot a bien fait, et qu'il ne faut pas défaire

Le reste du portage est juste : `#7c8699` partout où la maquette écrivait `#5f6880` (le
contraste a été respecté), aucun `all:unset`, aucun `https://` chargé, `insertAdjacentHTML`
conservé dans `appendLogLine`, `escapeHtml` et `safeColor` respectés ailleurs, les trois
états (chargement / vide / erreur) conservés sur chaque gabarit porté, et la pastille d'état
de l'avatar tranchée dans le bon sens — la règle morte `.bot-card.running::after` est
**déplacée** sur `.bot-avatar::after`, la classe `running` est enfin posée, et elle l'est
dans **les deux** branches de `renderBotsGrid`.

## Ce qui n'a pas été porté, faute de route — la liste à garder

- `msgs` par bot et statut `degraded` sur la carte de bot : `/api/bots` ne les sert pas.
- « Top interlocuteurs » de la vue conversations : `get_stats` ne renvoie aucune liste.
- Groupement des clés **par bot** : `api_key_status` a pour clé `(api_name, key_index)`,
  **aucune colonne bot**. Groupé par fournisseur. Voir [[regle-une-cle-api-par-bot]].
- Barres sous les tuiles « Erreurs 24 h » et « Utilisateurs 7 j » : pas de dénominateur.
- Occurrences 24 h, fichier source, trace dans le détail d'erreur : voir le point 3.

## Ce qu'il faut décider, et qui n'est pas du portage

**Plus rien n'écrit dans `error_events`.** `shared/shared_database.py:916` définit
`log_error_event(...)` et **aucun appelant n'existe dans le dépôt**. Les 10 lignes en base
datent du **8-9 juin 2026**. Conséquence : la vue « Analyse Erreurs » est vide en
permanence, la tuile « Erreurs (24 h) » affiche `0` quoi qu'il arrive, et la moitié erreurs
du bandeau d'alerte ne peut pas se déclencher. Ce n'est **pas** un défaut du Lot 2 — c'est
antérieur, et hors de son périmètre (« ne pas toucher au backend »). C'est un chantier à
part : soit rebrancher un `logging.Handler` sur `log_error_event`, soit retirer la vue.

## Recette encore due

`pyflakes` : propre (rien de nouveau ; le bruit existant est antérieur et hors Python
touché). `node --check` : vert sur les deux fichiers JS. **Le parcours au clic des 8 vues
n'a toujours pas été fait** — il demande le mot de passe du dashboard et un humain.

---

# LE LOT 3

## Où on en est

Lots 1 et 2 sont dans l'**arbre de travail** (`index.html`, `css/dashboard.css`,
`js/app.js`), relus et réparés, **non commités**. Le Lot 1 est commité à part (`a0be86e`),
**non poussé**.

Il reste **une seule chose** : le balisage des vues Twitch, que le Lot 2 devait porter
(point 9 de son plan) et n'a pas porté.

## Les règles n'ont pas changé

1. **Le backend ne change pas.** Aucune route, aucun schéma. Ce que la maquette montre et
   qu'aucune route ne sert est **retiré de la vue** et listé dans le rapport.
2. **Pas de React, pas de build**, pas de `npm`/`pnpm`, pas de CDN. JS vanille.
3. **Tout reste hors-ligne** : aucun `https://` chargé dans la page.
4. **Aucune fonction ne disparaît** : les 5 onglets Twitch, leurs `id` d'ancrage, leurs
   `onclick`, le toggle `chat.eventsub`, les confirmations destructives.
5. **Ne pas toucher à** `backend/` **ni aux tests.**

## Les fonctions, une par une

Toutes dans `js/app.js`. Référence visuelle : `dashboard/design_v2/template_pretty.html`.

1. **`renderTwitchBotView`** — l'ossature des onglets : panneaux `--bg-card` opaques, blocs
   imbriqués `#161628`, bordure `#23233a`, survol `#43436b`. C'est elle qui porte le plus
   d'`id` : les recopier **un par un**.
2. **`loadTwitchPresence`** — mêmes pastilles d'état que le reste du dashboard.
3. **`loadTwitchEvents`** — rangées de tableau comme `loadAuditLogs` : séparateur `#1c1c2f`,
   survol `rgba(255,255,255,0.02)`, action en pastille.
4. **`loadTwitchEconomy`** et **`loadTwitchListen`** — mêmes tableaux. ⚠️ Ce sont exactement
   les deux que `update_twitch.py` a prétendu porter sans y toucher : les **relire** avant
   de dire qu'elles sont faites.
5. **`renderRewardsTable`** — déjà porté au Lot 2, ne pas le refaire.

Chaque gabarit garde ses **trois états** : chargement, vide, erreur — habillés à la D.A., et
l'état vide doit dire *pourquoi* il est vide.

## Comment livrer

1. **Éditer les fichiers directement.** Pas de script Python jetable qui récrit `app.js` :
   c'est ce mécanisme qui a produit les trois ruptures de syntaxe du Lot 2, et son `Success`
   inconditionnel qui a caché ce qui n'avait pas été fait.
2. **Ne pas commiter, ne pas pousser, ne pas créer de branche.** La relecture commite.
3. **Livrer par groupes de 2 fonctions**, en s'arrêtant entre chaque.
4. **Rendre compte de ce qui n'a pas été fait**, nommément.

## Recette

- `node --check dashboard/frontend/js/app.js` **et** `charts.js` — la première chose, pas la
  dernière. Un `app.js` qui ne parse pas rend la page entièrement muette, sans erreur
  visible.
- `pyflakes`, puis `pytest` **seul** (la suite se bind le port 8599 et partage `data/`).
- Vérifier que chaque `getElementById` des blocs touchés trouve encore sa cible :
  un `id` retiré du HTML ne casse aucun test, il casse la page en silence.
- Lancer le dashboard **par le raccourci du Bureau**, et parcourir les **5 onglets Twitch au
  clic** — c'est là que vivent le plus de gestionnaires.
- Ne pas dire « c'est bon » avant que la **CI soit verte**.
