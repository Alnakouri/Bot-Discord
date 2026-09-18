# PLAN — Les astérisques, du harnais jusqu'aux fiches

Rédaction : Claude, le **2026-09-17**, à partir du run `tests/eval/reports/eval_20260917_1233.json`.
Exécution : **Antigravity**, sauf le LOT 4.

Cinq lots. Le **0 est livré** (`2e06d09`). Les lots 1 à 3 visent une seule cible mesurée,
par trois bouts différents. Le 4 attend un humain depuis le 15/09.

---

## ETAT AU 17/09 AU SOIR — tout est livre, une question reste ouverte

| lot | etat |
|---|---|
| **LOT 0** harnais | ✅ `2e06d09` — le juge lit le texte APRES le filtre du bot |
| **LOT 1** filet | ✅ `ec79b3f` — les 6 bots filtrent, verifie DANS chaque conteneur |
| **LOT 2** fiches | ✅ `ec79b3f` — les 5 autres ont pris la forme de celle de Sugar |
| **LOT 3** dur | ✅ `ec79b3f` — didascalies des pools d'Alfred retirees ; `*POUF*` garde (decision) |
| **MESURE** | ✅ les SIX au bareme 3, malena au 3e essai (quota) |
| **LOT 4** navigateur | ✅ decret bascule/relu/rebascule, bouton de redemarrage verifie cote `docker`, libelles honnetes |

    alfred 4.86 | maiq 4.46 | sheogorath 4.46 | sugar 4.42 | johnny 4.18 | malena 4.10

⚠️ **Deltas non comparables** au bareme 2 : l'entree du juge a change.

### La question que la mesure a tranchee — CORRIGEE le 18/09

Passe complete du **18/09 a quotas frais** (5 bots fiables, sheogorath non : un scenario
perdu). Comptes d'asterisques AVANT filtrage, contre le matin du 17 :

    bot          17/09   18/09
    sugar         0/17   11/17   <- sa fiche n'a PAS change
    alfred       16/17    9/17
    johnny       16/17   11/17
    sheogorath   17/17    9/17
    malena       11/17    7/17
    maiq          4/17    6/17

⚠️ **Lu tel quel, ce tableau ment.** Sugar n'a pas regresse : son ECHELON a change.
Gemini etait a sec, ministral-14b a repondu a sa place (15 reponses sur 17) — et ministral
etait mesure a 11/18 asterisques des le 04/09. Le chiffre colle.

**Ce qu'on peut conclure, une fois le modele tenu constant :** alfred et johnny sont
servis a 100 % par ministral dans LES DEUX runs, fiche reecrite entre les deux —
**16/17 -> 9/17** et **16/17 -> 11/17**. La reecriture des fiches (LOT 2) fait bien
chuter la production d'environ 40 %. Cela **corrige** la conclusion ecrite ici le 17/09 au
soir (« la fiche n'a presque rien change »), tiree de malena seule, dont le melange
d'echelons avait bouge. Voir
[[gotcha-le-compte-brut-est-fausse-par-l-echelon-qui-a-repondu]].

**Reserve qui reste ouverte — l'OUTIL pour la fermer est livre (18/09, `tests/eval/`) :**
depuis le LOT 0, l'historique rendu au modele contient ses propres reponses FILTREES — il
s'imite lui-meme, sans asterisques. La baisse peut venir de la fiche, de cet historique
assaini, ou des deux.

▶ **`python tests/eval/run_eval.py --historique-brut`** remet le texte NON filtre dans
`conversation_history` ; ce qui est NOTE reste le texte filtre. Le defaut ne bouge pas, et
c'est voulu : sur Discord, le tour suivant relit le message ENVOYE, donc filtre — un
harnais a historique brut mesurerait une conversation qui n'a jamais eu lieu
([[gotcha-le-harnais-mesure-le-modele-pas-le-bot]]). Le rapport porte `historique_brut`, et
un run experimental ne peut plus devenir en silence la reference du run normal suivant :
les deltas sont masques, exactement comme pour un barème different.
**Reste a faire : le run lui-meme** (un bot suffit, `--bot alfred` — il est a 100 %
ministral dans les deux passes, donc le modele y est constant).

**Amelioration du harnais : LIVREE le 18/09.** Le bloc AVANT/APRES nomme desormais, sous
chaque compte, l'echelon qui a repondu :

        - alfred       :  9/17  ->  0/17   (le filet fait le travail)
                          echelons : mistral/ministral-14b x17

Sans cette ligne, une bascule d'echelon se lit comme une regression de persona — c'est
exactement l'erreur commise le 17/09 au soir. L'echelon est capte en OBSERVANT
`tracer_appel` (l'espion delegue au vrai traceur, la base ne perd rien) plutot qu'en
ajoutant un parametre a `generate_response` : `shared/llm_cascade.py` est VENDORE dans les
six bots, et une commodite de harnais n'a pas a faire bouger le code de production.
Les anciens rapports, qui n'ont pas le champ, affichent « echelon inconnu » au lieu de
mentir. Une cascade entierement muette ne nomme AUCUN echelon (le dernier essai rate n'est
pas un auteur) — ce trou-la n'a ete vu qu'en rejouant les mutations.

### Ce que le run a trouve et qui est corrige

- `e50dc1d` — le **gras** devenait de l'italique (`**x**` -> `*x*`), et une **didascalie
  sans borne** a mange 200 caracteres de replique chez Alfred.
- `41955f6` — la reponse **brute** est gardee a cote de la filtree : sans elle, la
  question ci-dessus aurait coute un run entier a trancher.
- `a6a66ee` — un test prenait **310 s** a lui seul (un `git check-ignore` par lien).

### Ce qui reste, et qui n'est pas dans ce plan

- **Relancer une passe complete** quand les quotas seront frais, pour voir les six
  colonnes AVANT/APRES et trancher le LOT 2 sur les six.
- ⚠️ `Windows fatal exception: access violation` dans `test_anti_rattrapage_boucles.py:167`
  (boucle asyncio Windows). La suite finit verte, mais la ligne de resume disparait parfois.
- **NVIDIA** : tranche, il reste tel quel — [[decision-nvidia-reste-avec-la-borne-du-direct]].

---

## CE QUE LE RUN A MONTRÉ (le matin du 17/09, bareme 2)

Six bots, **barème 2**, `fiable: true` pour les six, **0 appel échoué, 0 score à ‑1**.

    bot            fidelite   ton_fr  anti_cont  anti_fuite  longueur   global
    sugar              4.10     4.70       5.00        5.00      5.00     4.76
    maiq               4.10     4.70       5.00        5.00      4.10     4.58
    sheogorath         3.80     4.90       5.00        4.50      3.10     4.26
    johnny             2.60     4.30       5.00        5.00      3.30     4.04
    malena             1.80     3.90       5.00        5.00      2.60     3.66
    alfred             1.90     4.20       5.00        5.00      1.40     3.50

`anti_contamination` et `anti_fuite` sont réglés. **Le seul critère faible est `fidelite` :
3.05.** Vingt-six verdicts sur soixante y tombent à 2 ou moins, et la même phrase revient :
*« a brisé les règles de narration »*, *« description narrative entre astérisques »*.

Compté sur les **102 réponses**, sans passer par le juge :

    bot          réponses contenant *…*   tête de cascade   règle anti-narration dans la fiche
    sugar                 0 / 17          flash-lite        « Tu ne fais QUE parler » (positive)
    maiq                  4 / 17          flash-lite        une ligne, sur les PARENTHÈSES seules
    malena               11 / 17          flash-lite        trois ❌ dont un sur les astérisques
    johnny               16 / 17          ministral-14b     quatre ❌, dont deux sur les astérisques
    alfred               16 / 17          ministral-14b     quatre ❌ + un MAUVAIS EXEMPLE décrit
    sheogorath           17 / 17          gpt-oss-120b      « 🚫 PAS DE NARRATION », la plus nette

**64 réponses sur 102.** Les six fiches l'interdisent toutes.

### Les deux conclusions faciles, et pourquoi le tableau les refuse

- **« C'est le modèle. »** Non : sugar 0, maiq 4 et malena 11 partagent la **même tête**.
  Le modèle aggrave — la sonde du 04/09 mesurait `ministral-14b` à 11/18 — il ne décide pas.
  [[gotcha-la-longueur-est-un-defaut-de-MODELE]] vaut pour la longueur, pas ici.
- **« C'est le volume d'interdiction. »** Non plus : **Sheogorath a la règle la plus nette
  et le pire chiffre.** Alfred a reçu deux renforcements (`4bb1ce4`, `4402e3d`) et reste à
  16/17. Empiler des ❌ n'a jamais rien donné — trois fois de suite.

Ce que Sugar a de différent n'est pas la force de sa règle, c'est sa **forme** : elle dit ce
qu'il FAIT (« tu ne fais que parler ») avant ce qu'il ne fait pas, et cite les tics **en
clair entre guillemets**, jamais entre astérisques. C'est une hypothèse, pas une preuve :
le LOT 2 est écrit pour qu'elle puisse être **réfutée** par la mesure.

---

## L'ORDRE, ET POURQUOI IL N'EST PAS NÉGOCIABLE

Le LOT 0 devait passer **en premier** : le harnais notait la sortie brute du modèle, donc
un filet ajouté à un bot n'aurait bougé **aucun** score et on aurait conclu à son échec.
Il est livré. Ensuite :

    LOT 1  le filet    garantit   ──┐
                                    ├── LOT 1 avant LOT 2 : le filet rend le résultat
    LOT 2  la fiche    oriente    ──┘   VISIBLE même si la fiche ne change rien.
    MESURE run complet des six          Première référence « produit », barème 3.
    LOT 3  le hors-LLM                  Ce qu'aucun des deux ne peut atteindre.
    LOT 4  le navigateur                Humain requis, indépendant du reste.

⚠️ Faire le LOT 2 **seul** serait le piège inverse du LOT 0 : si la fiche améliore les
choses sans filet, on ne saura pas ce qui a agi. Le filet d'abord donne un plancher ; la
fiche se juge ensuite **sur le texte d'avant filtrage**, que le rapport conserve.

---

# LOT 0 — ✅ LIVRÉ (`2e06d09`) — le harnais mesure le BOT, plus le modèle

Pour mémoire, et parce que les lots suivants s'appuient dessus :

- `SugarBot/sugar_filtres.py` (nouveau) — le filtre de Sugar est sorti de `bot_sugar.py`,
  qui importe `discord` et restait donc hors de portée du harnais.
- `Sheogorath/sheo_llm.py` — `filtre_sortie(texte, message_utilisateur=None)` regroupe les
  étapes sans état ; `postprocess_response` passe par elle. L'ordre écho → astérisques
  (correctif du 06/09) est préservé, et son verrou a suivi le code.
- `tests/eval/persona_loader.py` — `FILTRES` + `load_filtre(bot_id)`, qui rend **l'identité**
  pour un bot sans filtre : un harnais qui refuserait de mesurer les bots nus ne mesurerait
  plus rien.
- `tests/eval/runner.py` — applique `filtre_sortie(response, user_msg)`, **après** le repli
  `ECHEC_CASCADE` (c'est un marqueur du harnais, pas une réplique).
- `tests/eval/judge.py` — `VERSION_BAREME` 2 → 3. Le prompt du juge n'a pas bougé d'une
  ligne : c'est son **entrée** qui change, et elle déplace les notes.

7 verrous AST (`tests/test_verrou_filtre_sortie.py`), le principal vérifié par mutation.
Suite complète : **1045 verts**.

⚠️ **Limite connue, assumée** : le plafond de phrases de Sheo (`force_short_response`) se
calcule sur le message et tombe après les easter eggs — il reste **hors** du chemin mesuré.
Le `longueur` de Sheogorath est donc encore sous-mesuré. À savoir avant de lire le prochain
run ; à traiter seulement si ce critère devient la question.

---

# LOT 1 — le filet déterministe sur les quatre bots nus

**Alfred, Johnny, M'aiq, Malena.** Sheo a déjà écrit l'argument dans son propre code :
*« Une règle de prompt oriente ; elle ne garantit rien. Seul un filet déterministe
garantit. »*

## 1.1 — Deux traitements, à ne jamais confondre

- **Didascalie** (`*Soupir imperceptible*`, `*pose son torchon*`) → **tout le segment tombe**.
- **Emphase** (`*The Times*`, `*très*`) → **les marqueurs tombent, les mots restent**.

La logique existe, curée par deux passages en production : `SugarBot/sugar_filtres.py`.
**La reprendre, ne pas la réécrire.** Elle protège déjà deux pièges payés cher : un
impératif de dialogue (« souris ! ») n'est pas une didascalie, et `le_dev` n'est pas
de l'italique.

## 1.2 — Un module par bot, sans `discord`

Créer `Alfred/alfred_filtres.py`, `JohnnyBot/johnny_filtres.py`, `MaiqBot/maiq_filtres.py`,
`MalenaBot/malena_filtres.py`, chacun exposant :

```python
def filtre_sortie(texte, message_utilisateur=None): ...
```

`message_utilisateur` est facultatif et peut être ignoré : il existe pour que les six bots
présentent **la même porte**, appelable par le harnais sans savoir lequel il tient.

⚠️ Copie **inline par bot**, pas un import obligatoire de `shared/`
([[decision-independance-stricte-vendoring-core]] : chaque bot reste déployable seul). Si le
code passe par `tools/vendor_core.py`, mettre à jour **les deux** listes — celle du copieur
et celle de la sonde de dérive ([[gotcha-deux-listes-vendoring]]).

## 1.3 — Où brancher, bot par bot (relevé le 17/09)

| bot | point de branchement | remarque |
|---|---|---|
| Alfred | `bot_alfred.py:2096-2098` → remplacer les 3 `re.sub` par `filtre_sortie` | l'envoi est juste après, ligne 2100 |
| Johnny | `bot_johnny.py:1164-1166`, même forme | ⚠️ son `_strip_stage_directions` de la ligne 528 ne concerne **que** une punchline Twitch : ne pas croire le bot déjà équipé |
| M'aiq | `bot_maiq.py:1710-1712`, même forme | envoi ligne 1715 |
| Malena | **aucun** nettoyage aujourd'hui, et **5 `return _texte_branche`** dispersés dans sa cascade INLINE (`bot_malena.py:274, 287, 320, 355, 399`) + 2 envois (`:841` et `:968`, la « mention manquée ») | renommer `generate_response_hybrid` en `_generate_response_hybrid_brut` et écrire un mince enveloppe qui filtre le retour : **une** modification couvre les 5 sorties et les 2 envois |

⚠️ Malena est le cas à ne pas bâcler : filtrer à ses deux `reply()` laisserait le prochain
chemin d'envoi à découvert. C'est [[gotcha-appels-fournisseur-hors-cascade]] transposé —
compter les SORTIES, pas les fonctions.

## 1.4 — Déclarer les filtres au harnais

Ajouter les quatre entrées dans `tests/eval/persona_loader.FILTRES`. Sans cela, le LOT 1
est invisible au score — c'est exactement le défaut que le LOT 0 vient de corriger.

## 1.5 — Verrous (compléter `tests/test_verrou_filtre_sortie.py`)

1. `FILTRES` contient **les six** bots. Pas cinq ([[gotcha-un-bot-sur-six-manque-toujours]]).
2. Pour chacun : `filtre_sortie` retire une didascalie **entière** et ne laisse **aucun**
   astérisque, sur les cas réels du run (`*Soupir imperceptible, mais audible…*`,
   `*Souffle sur ma clope imaginaire*`, `*soupir dramatique*`, `*The Times*`).
3. Pour chacun : ne coupe **pas** « Souris ! », ne touche **pas** `le_dev`.
4. AST **sur le fichier du bot**, visant le **NOM** : `filtre_sortie` est appelée, et les
   `re.sub(r"<fact>…` remplacés ont **disparu** ([[gotcha-import-ajoute-mais-pas-cable]],
   [[gotcha-verrou-trop-faible]]).
5. Pour Malena : vérifier que la fonction publique `generate_response_hybrid` passe par le
   filtre, et qu'aucun `return _texte_branche` ne subsiste hors de l'enveloppe.

**Fin du lot** : suite complète verte, et `python tests/eval/run_eval.py --bot alfred` rend
un texte sans astérisque dans le rapport.

---

# LOT 2 — la forme de la règle, portée aux cinq autres fiches

## 2.1 — L'hypothèse, et ce qui la réfuterait

La phrase de Sugar (`SugarBot/sugar_data.py:34`) :

> *Tu ne fais QUE parler : JAMAIS de didascalie ni d'action narrée — ni entre astérisques,
> ni en clair (« soupir sucré », « glisse un regard en coin », « sourire en coin »).
> Tu ne décris pas tes gestes, mimiques ou soupirs : tu ne mets que tes répliques.*

Trois traits : elle **nomme le comportement attendu** en premier, elle **cite les tics en
clair** entre guillemets français, et elle **ne montre jamais** la forme interdite.

**Hypothèse** : c'est cette forme qui tient, pas la sévérité.
**Ce qui la réfute** : si, après le LOT 2, les comptes d'astérisques **avant filtrage** ne
baissent pas, l'hypothèse est morte — on le dit, on la retire du plan, et le filet du LOT 1
reste la seule réponse. Le rapport conserve le texte d'avant filtrage : la mesure est
disponible, elle n'exige aucun outil neuf.

## 2.2 — Où intervenir

| fiche | lignes à refondre | état actuel |
|---|---|---|
| `Alfred/alfred_data.py` | 14-22, et la ligne 50 (parenthèses) | quatre ❌ + un MAUVAIS EXEMPLE décrit |
| `JohnnyBot/johnny_data.py` | 18-21 | quatre ❌ |
| `MalenaBot/malena_data.py` | 18-20 | trois ❌ |
| `MaiqBot/maiq_data.py` | 62 | **une seule ligne**, et seulement sur les parenthèses |
| `Sheogorath/sheo_data.py` | 691-692 (et 757) | la plus nette des six… et 17/17 |

## 2.3 — Les trois interdits de ce lot

1. **Ne pas ajouter un troisième renforcement chez Alfred.** Deux ont échoué. Changer la
   FORME, pas le volume.
2. **Ne jamais écrire la démonstration de ce qu'on interdit**
   ([[gotcha-le-prompt-enseigne-le-tic-interdit]], deux occurrences déjà — un prompt qui
   écrit `*allume une clope*` enseigne le geste qu'il condamne).
3. **Chercher d'abord la PERMISSION.** Avant de réécrire une règle, relire la fiche entière
   à la recherche de ce qui **autorise** le comportement ailleurs
   ([[gotcha-une-permission-bat-une-demonstration]]) : chez Johnny, c'est ce qui explique sa
   longueur, et c'est écrit dans `CASCADES_PERSONA`.

**Fin du lot** : suite verte, fiches relues, et **aucune** nouvelle démonstration introduite
(un verrou existe déjà pour ça — le laisser travailler).

---

# MESURE — le run complet, entre le LOT 2 et le LOT 3

    python tests/eval/run_eval.py          # les six, ~1 h, à un moment creux

- Lire le **bloc de santé AVANT les scores** (`scores_a_moins_un`, `fiable`). Un bot non
  fiable : regarder les cooldowns et **relancer ce bot seul** (`--bot <id>`) avant de
  conclure quoi que ce soit ([[gotcha-run-eval-borne-par-le-quota]]).
- Les deltas resteront **masqués** : le rapport du 17/09 est en barème 2, celui-ci en 3.
  C'est voulu. Ce run devient la première référence « produit ».
- La mesure qui tranche n'est pas le score du juge, c'est le **compte d'astérisques avant
  filtrage**, bot par bot. **64 sur 102** est le chiffre à battre, et il se compte sans le
  juge — donc sans quota, et sans discussion.

---

# LOT 3 — les didascalies EN DUR, que ni le filet ni la fiche n'atteignent

Elles ne passent pas par le LLM : une règle de persona ne protège que ce qui traverse le
modèle (leçon du 16/09 chez Sheo).

- `Alfred/bot_alfred.py:1612` `*pose son torchon*` et `:1615` `*soupir britannique*` —
  pool de sanction « chant », envoyé tel quel. Vraies didascalies : **retirer**.
- `Alfred/bot_alfred.py:933,934` `*chant*`, `*bruit*` — de l'**emphase** : marqueurs
  retirés, mots gardés. Ne pas amputer la réplique.
- `Sheogorath/sheo_punishments.py` (`*POUF*`, `*TRANSFORMATION !*`, `*Soupir*`) — **à
  trancher, pas à corriger d'office.** `*POUF*` est un effet sonore de sort : ça peut être
  voulu ([[gotcha-un-defaut-peut-etre-une-fonctionnalite]]). **Poser la question** avant de
  toucher ; `*Soupir*` est un cas différent, c'est une vraie didascalie.

⚠️ Ne PAS supprimer par motif textuel : ces littéraux vivent dans des listes, et une coupe
à la regex casse la syntaxe ou efface une entrée voisine
([[gotcha-suppression-par-motif-textuel]] — pyflakes AVANT pytest).

**Fin du lot** : suite verte, et une relecture des **littéraux** des pools, pas du code
([[gotcha-persona-fuite-dans-le-partage]]).

---

# LOT 4 — Le dashboard, au navigateur — exécution : **Claude**, pas Antigravity

*(ouvert depuis le 15/09 ; il demande un humain, des clics et des captures.)*

1. **Le toggle du décret** — `data/bot_features.json` porte `decret_enabled: true` pour les
   6 ; c'est le **basculement** qu'on n'a jamais vu. Basculer, relire le fichier,
   rebasculer, relire.
2. **Le bouton de redémarrage** — `tests/test_dashboard_restart.py` existe ; le clic, non.
   Le faire sur **un seul bot**, et vérifier côté `docker ps`.
3. **Les graphes et le statut réel** — vérifier que « CONNECTÉ » mesure bien la connexion
   ([[gotcha-un-relooking-change-ce-que-le-libelle-affirme]]).
4. **Capture d'écran à chaque étape**, jointe au compte rendu.

⚠️ Le redémarrage touche des bots **en service**. Le faire hors d'un moment où quelqu'un
leur parle, et sur un seul.

⚠️ Avant de conclure qu'un panneau ne marche pas : vérifier le sélecteur de bot — « Tous les
bots » MASQUE les panneaux par-bot ([[gotcha-regarder-l-ecran-avant-le-code]]).

---

## Ce qui n'est PAS dans ce chantier

- **Changer une tête de cascade pour régler les astérisques.** Mesuré : sugar 0, maiq 4 et
  malena 11 partagent la même. Ce serait du brassage.
- **La verbosité de Johnny.** Trois interventions, trois échecs (modèle, prompt, sonde). Ne
  rien faire reste défendable ; c'est écrit dans `CASCADES_PERSONA`.
- **Toucher au juge.** Il a changé de barème le 17/09 ; on ne déplace pas l'instrument et la
  pièce dans le même geste.
- **Le plafond de phrases de Sheo dans le harnais** — limite connue du LOT 0, à ouvrir
  seulement si `longueur` devient la question.
- **Twitch**, gelé depuis le 08/09.
- **Les handles de M'aiq** (`tools/sonde_handles_db.py`) : indépendant, et il faut des
  points d'uptime croissant.
