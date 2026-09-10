# PLAN — Dashboard v2 : le Lot 3 est livré et relu

Rédaction : Claude, le **2026-09-10**. Exécution du Lot 3 : **Antigravity**, relu et
corrigé le même jour. Le Lot 3 était le dernier du portage : **le dashboard v2 est
complet.**

---

# RAPPORT DE RELECTURE DU LOT 3 (10/09)

## Le réflexe qui a servi, et ce qu'il a dit cette fois

Diff annoncé : « les 5 vues Twitch ». Diff réel : **36 insertions dans `app.js` seul**.
C'est exactement le signal de [[gotcha-portage-maquette-roles-couleurs]] — comparer la
taille du diff au périmètre annoncé avant de relire ligne à ligne.

**Mais cette fois le signal était un faux positif, et c'est le plan qui avait tort.**
Vérification faite fonction par fonction : la quasi-totalité du balisage des vues Twitch
vit dans **`index.html`**, pas dans `app.js`. Ce que `app.js` sert vraiment, c'est cinq
gabarits — la carte d'abonnement, la rangée de liens, la rangée de récompenses, la rangée
de classement — et des remplissages de formulaire sans balisage du tout. Le Lot 3 les a
tous touchés. **Il n'a pas sous-livré : le plan surestimait la surface JS.**

Deux conséquences à retenir pour la prochaine fois :

- `loadTwitchListen` **n'a aucun gabarit** : cinq `getElementById(...).value = ...`. Le
  plan lui demandait « les mêmes tableaux » — il n'y a pas de tableau. Ne pas reprocher à
  une livraison de ne pas avoir fait ce qui n'existe pas.
- `loadTwitchEvents` **délègue entièrement** à `renderRewardsTable`, que le plan disait de
  ne PAS refaire. Refait quand même — mais l'ajout (`padding:12px`, action alignée à
  droite) est cohérent avec les autres tableaux. Gardé.

Et la peau des panneaux Twitch était **déjà bonne** sans y toucher : le Lot 1 a récrit
`.glass` en `--bg-card` opaque et posé `--bg-panel-inner: #161628` / `--border-glass:
#23233a`. Les vues Twitch les héritent par les jetons. Il n'y avait pas d'ossature à
porter.

## Les défauts corrigés à la relecture

**1. Le badge de présence annonçait une connexion que rien ne mesure.** Le libellé est
passé de « Active / Inactive » à **« CONNECTÉ / DÉCONNECTÉ »**, sous un titre « Statut de
Connexion ». Or la valeur lue est `configData[botId].enabled` de `/api/twitch` : c'est le
toggle **« Activer la surveillance Twitch »** des annonces, pas un état de connexion au
chat. Vérifié côté backend : `/api/twitch/chat/{bot}` renvoie `cfg.get("chat", {})`, qui
n'a **aucun** champ de connexion — **aucune route ne sert cet état**. Un bot au chat
connecté mais aux annonces coupées se serait affiché « DÉCONNECTÉ ». C'est la règle 1 du
plan : ce qu'aucune route ne sert ne s'invente pas. Libellé rendu exact
(« Surveillance active / inactive »), titre du panneau corrigé en « Surveillance Twitch ».

**2. Le même badge perdait sa pastille.** `badgeEl.className = ""` effaçait **toutes** les
classes, dont `.badge` — qui porte à lui seul le `padding`, le `border-radius: 20px`, la
taille et les majuscules. Restaient un fond et une couleur inline sans géométrie : un
liseré coloré derrière le texte, pas une pastille. Corrigé en réutilisant les pastilles
**qui existent déjà** dans le dashboard, `.badge.running` / `.badge.stopped` — ce que le
plan demandait mot pour mot.
⚠️ Au passage : `badge-success` et `badge-secondary`, utilisées ici depuis toujours, ne
sont **définies nulle part** dans `dashboard.css`. Le bascule de classe de la v1 ne
changeait donc rien à l'écran. Références mortes retirées.

**3. Trois boutons en `all:unset`.** Le rapport du Lot 2 listait « aucun `all:unset` »
parmi les choses **à ne pas défaire** ; le Lot 3 en a réintroduit trois. Sur un `<button>`,
`all:unset` est une déclaration d'auteur qui s'applique dans tous les états : elle supprime
l'anneau de focus de l'agent utilisateur, et le bouton devient **invisible au clavier** —
sans que rien ne casse, ni à l'écran ni dans un test. Remplacé par une remise à zéro qui ne
touche qu'à ce qu'il faut (`appearance`, `background`, `margin`, `padding`, `font`).

**4. Le message d'annonce personnalisé est devenu illisible.** La carte d'abonnement
affichait le message en clair ; le portage l'a réduit à une pastille « Perso » avec le
texte en `title`, donc **au survol seulement**. Or c'est le seul endroit du dashboard où ce
message se lit : il n'existe aucune route d'édition d'un abonnement. Invisible au tactile,
invisible au clavier, invisible à la lecture d'écran. La pastille est gardée (densité de la
maquette) et la ligne en clair revient sous la carte quand un message existe.

**5. Un survol qui ne suivait pas la règle.** Le classement économique éclaircissait ses
rangées en `#1c1c2f` là où le journal d'audit et les récompenses utilisent
`rgba(255,255,255,0.02)`. Aligné.

## Ce que ce lot a bien fait

Livré **en éditant les fichiers directement** — aucun script Python jetable dans
`dashboard/frontend/`, et `node --check` vert **à la livraison**, pas après réparation.
C'est la leçon du Lot 2 ([[gotcha-script-jetable-dit-success]]) appliquée. `escapeHtml`
respecté partout dans les nouveaux gabarits, y compris dans les attributs (il échappe bien
`"` et `'`), `insertAdjacentHTML` conservé, aucun `https://` chargé, les confirmations
destructives intactes (`confirmDialog` sur `deleteTwitchSubscription`), et les **13 `id`**
des blocs touchés vérifiés un par un : tous présents dans `index.html`, exactement une
fois chacun.

## Ce qui n'a pas été porté, faute de route — la liste à garder

- **État de connexion réelle au chat Twitch** : n'existe dans aucune route. Voir le point 1.
- Les listes de la vue Lot 2 restent valables : `msgs` par bot, statut `degraded`,
  « Top interlocuteurs », groupement des clés par bot, dénominateurs des tuiles
  « Erreurs 24 h » et « Utilisateurs 7 j ».

## Détail annexe

`dashboard/design_v2/extract.py` portait un chemin absolu `I:\IA\...` en dur — le motif
même que le rapport du Lot 2 reprochait aux scripts jetables, mais celui-ci est **commité**.
Ancré sur `Path(__file__).parent`. Sa sortie `template_extracted.json` (215 Ko,
régénérable, jamais suivie) est sortie de l'arbre.

## Recette jouée

- `node --check` : **vert** sur `app.js` et `charts.js`, avant et après la relecture.
- `pyflakes` : **inchangé** (le bruit listé est antérieur, aucun Python de production
  touché).
- `pytest` seul : **900 tests, 0 échec**, code de sortie 0.
- Les 13 `getElementById` des blocs touchés : cibles vérifiées dans `index.html`.

## ⚠️ Ce qui reste dû, et qui demande un humain

**Le parcours au clic des 5 onglets Twitch n'a pas été fait** — il demande le mot de passe
du dashboard. C'est là que vivent le plus de gestionnaires. À faire par le raccourci du
Bureau, sur les cinq sous-onglets : Présence & connexion, Événements & Rewards, Habitués &
éco, Écoute live, Annonces.

**Et la CI n'a pas encore vu ce commit.** Ne pas dire « c'est bon » avant qu'elle soit
verte ([[feedback-le-local-ment-sans-cles]]).

---

# CE QUI RESTE APRÈS LE PORTAGE

Le dashboard v2 est complet : les 8 vues du Lot 2 et les 5 onglets Twitch du Lot 3.

## Le chantier à trancher, hors portage

**Plus rien n'écrit dans `error_events`.** `shared/shared_database.py:916` définit
`log_error_event(...)` et **aucun appelant n'existe dans le dépôt** ; les 10 lignes en base
datent du 8-9 juin 2026. Conséquence : la vue « Analyse Erreurs » est vide en permanence,
la tuile « Erreurs (24 h) » affiche `0` quoi qu'il arrive, et la moitié erreurs du bandeau
d'alerte ne peut pas se déclencher. Deux issues, à arbitrer : rebrancher un
`logging.Handler` sur `log_error_event`, ou retirer la vue. **Ce n'est pas du portage** —
ça touche au backend, que les trois lots avaient interdiction de toucher.
