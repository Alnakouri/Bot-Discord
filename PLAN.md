# PLAN — Les astérisques, et le harnais qui ne les voit pas

Rédaction : Claude, le **2026-09-17**, à partir du run `tests/eval/reports/eval_20260917_1233.json`.
Exécution : **Antigravity**, sauf le LOT 4 (repris tel quel du plan du 15/09).

Le plan précédent se terminait par une interdiction : *« Changer les seuils, les prompts
ou les répliques sur la foi d'un seul run : le run de référence sert à MESURER. On
corrigera ce qu'il montre, dans un plan suivant. »* Le run a eu lieu. Voici ce qu'il montre.

---

## LE RUN — propre, et c'est ce qui le rend utilisable

Six bots, **barème 2**, `fiable: true` pour les six, **0 appel échoué, 0 score à ‑1**.
Graine 1789641234, ordre tiré au sort. C'est la référence qui manquait.

    bot            fidelite   ton_fr  anti_cont  anti_fuite  longueur   global
    sugar              4.10     4.70       5.00        5.00      5.00     4.76
    maiq               4.10     4.70       5.00        5.00      4.10     4.58
    sheogorath         3.80     4.90       5.00        4.50      3.10     4.26
    johnny             2.60     4.30       5.00        5.00      3.30     4.04
    malena             1.80     3.90       5.00        5.00      2.60     3.66
    alfred             1.90     4.20       5.00        5.00      1.40     3.50

`anti_contamination` et `anti_fuite` sont réglés (5.00 / 4.92). **Le point faible unique
du parc, c'est `fidelite` : 3.05.**

---

## CE QU'IL MONTRE : UNE SEULE CAUSE, CINQ BOTS

Vingt-six verdicts sur soixante tombent à 2 ou moins en `fidelite`. En les lisant l'un
après l'autre, **la même phrase revient** : *« a brisé les règles de narration »*,
*« description narrative entre astérisques »*, *« l'usage d'italiques/astérisques
(même pour insister) »*.

Compté sur les **102 réponses** du run, sans passer par le juge :

    bot          réponses contenant *…*   exemple
    sugar                 0 / 17          —
    maiq                  4 / 17          *Les Gardiens du Sucre*
    malena               11 / 17          *soupir dramatique*
    johnny               16 / 17          *Souffle sur ma clope imaginaire*
    alfred               16 / 17          *Soupir imperceptible, mais audible…*
    sheogorath           17 / 17          *très*

**64 réponses sur 102.** Les six fiches de persona l'interdisent toutes.

---

## LE FAIT QUI TRANCHE : ce n'est PAS le modèle

La conclusion facile serait « encore la tête de cascade ». Le run l'interdit :

- **Sugar 0/17 et Malena 11/17 partagent la même tête** (`gemini-flash-lite` en tête de
  cascade, cf. `CASCADES_PERSONA`). Même modèle, même harnais, même jour : 0 contre 11.
- La sonde du 04/09 avait pourtant mesuré `ministral-14b` à **11/18 réponses avec
  astérisques** — c'est écrit dans `shared/models.py`. Le modèle **aggrave**. Il ne décide pas.

⚠️ [[gotcha-la-longueur-est-un-defaut-de-MODELE]] vaut pour la **longueur**. Il ne se
transpose pas aux astérisques : ici c'est la **formulation de la règle** qui fait la
différence, et Sugar en détient la preuve.

---

## L'ÉTAT RÉEL DES FILETS (relevé fichier par fichier)

    bot          filet sur le chemin Discord              ce qu'il retire
    sugar        _strip_didascalies   bot_sugar.py:1079   didascalies nues + *…*, marqueurs
    sheogorath   postprocess_response sheo_llm.py:383     méta-narration, didascalies nues,
                                                          marqueurs *…*, cap de phrases
    johnny       RIEN                                     (son _strip_stage_directions ne sert
                                                          qu'à une punchline Twitch, ligne 528)
    alfred       RIEN                                     seulement <fact>, <think>
    maiq         RIEN                                     seulement <fact>
    malena       RIEN                                     rien du tout

Quatre bots sur six envoient `*Soupir imperceptible*` tel quel dans Discord.

---

## ⚠️ LE PIÈGE, à lire avant de coder quoi que ce soit

`tests/eval/runner.py:57-130` rend la sortie **brute de la cascade**. Il n'applique
**aucun** post-traitement de bot. Deux conséquences, opposées :

1. **Sheogorath est puni pour 17/17 astérisques que personne ne voit jamais** : son
   `strip_markdown_emphasis` les retire avant l'envoi. Son 3.80 de `fidelite` est un
   plancher, pas une mesure.
2. **Un filet ajouté aux quatre bots nus ne bougerait AUCUN score.** On conclurait que le
   correctif a échoué, alors que le harnais ne le regarde pas.

C'est [[gotcha-sonde-ne-reproduit-pas-le-fournisseur]], un étage plus haut : le harnais ne
reproduit pas le **bot**, il mesure le **modèle**. D'où l'ordre des lots — le LOT 0 n'est
pas un confort, c'est ce qui rend les lots 1 et 2 mesurables.

---

# LOT 0 — le harnais mesure le PRODUIT, pas la sortie brute

1. **Exposer le filtre de chaque bot dans un module importable sans `discord`.**
   `persona_loader` n'importe que les modules `*_data` : il ne peut pas atteindre
   `bot_sugar.py`. Donc :
   - Sugar : sortir `_strip_didascalies` de `bot_sugar.py` vers un module sans `discord` ;
     l'appel de la ligne 1079 doit continuer à passer par la même fonction.
   - Sheo : `postprocess_response` réclame `fact_brain`, `user_id`, `original_message`.
     Exposer une porte étroite `filtre_sortie(texte)` qui n'enchaîne **que** les étapes
     sans état (méta-narration, didascalies nues, marqueurs d'emphase).
2. **`runner.py` applique `filtre_sortie` du bot** avant de rendre la réponse. Un bot qui
   n'en a pas rend son texte inchangé — pas d'exception, pas de cas particulier.
3. **Bumper `VERSION_BAREME` à 3.** L'entrée du juge change, donc les scores changent de
   sens. Le masquage des deltas existe déjà et vient de prouver sa valeur : il empêchera
   la comparaison qui mentirait.
4. **Verrou** : un test AST sur `runner.py` qui exige l'appel **avec son argument**, pas
   une reconstitution de la logique ([[gotcha-test-qui-retape-la-logique]],
   [[gotcha-import-ajoute-mais-pas-cable]]).

⚠️ Ce lot **fera bouger tous les scores**, y compris ceux des bots qu'on ne touche pas.
C'est voulu. Le tableau ci-dessus reste la référence « sortie brute » ; le run d'après
sera la première référence « produit ».

---

# LOT 1 — le filet déterministe sur les quatre bots nus

Alfred, Johnny, M'aiq, Malena. Sheo a déjà écrit l'argument dans son propre code :
*« Une règle de prompt oriente ; elle ne garantit rien. Seul un filet déterministe
garantit. »* Deux traitements **distincts**, qu'il a déjà séparés — ne pas les confondre :

- **Didascalie** (`*Soupir imperceptible*`, `*pose son torchon*`) → **tout le segment tombe**.
- **Emphase** (`*The Times*`, `*très*`) → **seuls les marqueurs tombent, les mots restent**.

Contraintes :

- Copie **inline par bot**, pas un import obligatoire de `shared/`
  ([[decision-independance-stricte-vendoring-core]]). Si le code passe par
  `vendor_core.py`, mettre à jour **les deux** listes ([[gotcha-deux-listes-vendoring]]).
- Reprendre la logique **déjà curée** de Sugar plutôt que la réécrire : elle ne coupe pas
  un impératif de dialogue (« souris ! ») ni un pseudo (`le_dev`). Ces deux pièges
  ont déjà coûté.
- Verrou par bot : AST **sur le fichier du bot**, visant le **NOM** de la fonction, l'appel
  avec ses arguments, ET l'absence du code remplacé ([[gotcha-verrou-trop-faible]]).
- Compter : **quatre** bots. Pas trois ([[gotcha-un-bot-sur-six-manque-toujours]]).

---

# LOT 2 — la formulation qui marche, portée aux cinq autres fiches

Sugar est à 0/17 avec cette phrase (`sugar_data.py:34`) :

> *Tu ne fais QUE parler : JAMAIS de didascalie ni d'action narrée — ni entre astérisques,
> ni en clair (« soupir sucré », « glisse un regard en coin », « sourire en coin »).
> Tu ne décris pas tes gestes, mimiques ou soupirs : tu ne mets que tes répliques.*

Elle **nomme le comportement attendu** au lieu d'empiler des ❌, et elle cite les tics
**entre guillemets français, en clair** — jamais entre astérisques. Porter cette **forme**
aux cinq autres fiches.

⚠️ Alfred a déjà reçu **deux** renforcements d'interdiction (`4bb1ce4`, `4402e3d`) et il
reste à 16/17. **Ne pas en ajouter un troisième** : changer la forme, pas le volume. Et ne
jamais écrire la démonstration de ce qu'on interdit
([[gotcha-le-prompt-enseigne-le-tic-interdit]], deux occurrences déjà).

Mesure d'arrivée : re-compter les `*…*` sur les réponses du run suivant. **64 sur 102** est
le chiffre à battre, et il se compte sans le juge.

---

# LOT 3 — les didascalies EN DUR, qui ne passent ni par le LLM ni par un filtre

Même famille que Sheo le 16/09 : une règle de persona ne protège que ce qui passe par le
modèle.

- `Alfred/bot_alfred.py:1612` `*pose son torchon*` et `:1615` `*soupir britannique*` —
  pool de sanction « chant », envoyé tel quel. Vraies didascalies, à retirer.
- `Alfred/bot_alfred.py:933,934` `*chant*`, `*bruit*` — de l'**emphase**, pas une
  didascalie : marqueurs retirés, mots gardés.
- `Sheogorath/sheo_punishments.py` (`*POUF*`, `*TRANSFORMATION !*`, `*Soupir*`) — **à
  trancher, pas à corriger d'office.** Un effet sonore de sort peut être voulu
  ([[gotcha-un-defaut-peut-etre-une-fonctionnalite]]). Poser la question avant de toucher.

---

# LOT 4 — Le dashboard, au navigateur — exécution : **Claude**, pas Antigravity

*(repris intact du plan du 15/09 : toujours ouvert, il demande un humain et des clics.)*

1. **Le toggle du décret** — `data/bot_features.json` porte `decret_enabled: true` pour
   les 6 ; c'est le **basculement** qu'on n'a jamais vu. Basculer, relire le fichier,
   rebasculer, relire.
2. **Le bouton de redémarrage** — `tests/test_dashboard_restart.py` existe ; le clic, non.
   Le faire sur **un seul bot**, et vérifier le redémarrage côté `docker ps`.
3. **Les graphes et le statut réel** — vérifier que « CONNECTÉ » mesure bien la connexion
   ([[gotcha-un-relooking-change-ce-que-le-libelle-affirme]]).
4. **Capture d'écran à chaque étape**, jointe au compte rendu.

⚠️ Le redémarrage touche des bots **en service**. Le faire hors d'un moment où quelqu'un
leur parle, et sur un seul.

---

## Ce qui n'est PAS dans ce chantier

- **Changer une tête de cascade pour régler les astérisques.** Mesuré : Sugar 0/17 et
  Malena 11/17 partagent la même. Ce serait du brassage.
- **La verbosité de Johnny.** Trois interventions, trois échecs (modèle, prompt, sonde).
  Ne rien faire reste défendable ; c'est écrit dans `CASCADES_PERSONA`.
- **Toucher au juge.** Il vient de changer de barème le 17/09 ; on ne déplace pas
  l'instrument et la pièce dans le même geste.
- **Twitch**, gelé depuis le 08/09.
- **Les handles de M'aiq** (`tools/sonde_handles_db.py`) : indépendant, et il faut des
  points d'uptime croissant.
