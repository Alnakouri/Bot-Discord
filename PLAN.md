# PLAN — SUITE 8-ter : Sugar tutoie le chat depuis SUITE 8-bis

Rédaction : Claude, le **2026-09-27**. Exécution : **Antigravity**, sauf les étapes marquées
**[Ahmed]**. Plan précédent (SUITE 8-bis, livré `57c78c8`) lisible dans git
(`942634a:PLAN.md`).

**Décision d'Ahmed (27/09)** : SUITE 8-bis **reste en prod** pendant ce chantier. Pas de
revert.

Fichiers, **seulement au LOT 3** : `shared/twitch/dispatch.py`
(`TYPES_DE_QUESTION_JEU_PAR_BOT`, l.887–893) et `tests/test_phrase_de_lien_jeu_en_cours.py`.

---

## LE CONSTAT (relu par Claude sur les sorties brutes, 27/09)

Scratch `221acb3a…/scratch/`. Est comptée comme tutoiement toute phrase contenant `tu`,
`ton`, `ta`, `tes`, `toi`, `viens`, en mots entiers, **sauf** une expression figée
(« en veux-tu en voilà », phrase 17 du contrôle).

| série | tutoiement | dont tu et vous mélangés |
|---|---|---|
| SUITE 5 B2 | 0/17 | 0 |
| SUITE 8 A (prod d'avant) | 0/16 | 0 |
| SUITE 8-bis LOT 1 (par type) | **3/24** | — |
| SUITE 8-bis contrôle (**code en prod**) | **8/18** | **2** |

Les deux phrases mélangées :
> Combien d'épées rouillées **ton** forgeron a-t-il déjà pliées en deux en Bohême ? **Venez** nous raconter vos pires ratés sur Discord !
> Bohemia **vous** a fait suer sang et eau ou juste baver sur votre écran ? **Viens** en débattre sur Discord.

La clause de Sugar dit pourtant « Vouvoie le chat : ils sont plusieurs. » (`dispatch.py`
l.866). La phrase de type, ajoutée **après** la clause, est la seule chose qui a changé.

**Deux écarts de la livraison précédente, à ne pas reproduire** :
1. Antigravity a annoncé « tous les critères passent ». Le LOT 1 fixait « vouvoiement
   ≤ 1/24 » ; il était à **3/24**.
2. La passe de contrôle du LOT 4 ne reprenait que 3 critères (faute du plan). **Ici, TOUTES
   les passes comptent TOUS les critères du tableau du LOT 1**, et le compte rendu donne
   chaque ligne, y compris celles qui échouent.

**Hypothèse, à vérifier par ce plan** : la phrase de type parle du chat à la troisième
personne (« leur demande de DÉSIGNER **leur** préféré ») et arrive en fin d'instruction,
après le rappel du vouvoiement. Le modèle finit par s'adresser à UNE personne : « quel est
**ton** favori ».

---

# LOT 0 — Avant toute passe

1. Lire la consommation du jour dans `data/api_usage.db`, en lecture seule, pour Sugar et
   Gemini (≈ 105 appels déjà faits aujourd'hui). Si Sugar est en live sur `#ma_streameuse`,
   **attendre la fin du live**.
2. Toutes les passes : **`--pause 10`**, **une série à la fois** (limite de 15 requêtes par
   minute sur `gemini-3.5-flash-lite`).
3. **Ne pas lancer `tools/sonde_phrase_de_lien.py --help`** (options l.239–275).

# LOT 1 — Mesurer (aucune modification du code de prod)

On mesure **le vrai code en prod**, rotation comprise : **pas de `--clause-jeu`**. Les
variantes passent par `--remplace` / `--par` (`tools/sonde_phrase_de_lien.py` l.160–188),
qui modifient l'instruction juste avant l'appel au modèle et **lèvent une erreur** si le
texte à remplacer n'y figure pas exactement une fois.

Commun aux trois séries : `--bot sugar --tete gemini --jeu "Kingdom Come: Deliverance II"
--n 18 --pause 10`, fiche réelle. **54 appels** au total, plus les secondes chances.

| série | `--remplace` | `--par` |
|---|---|---|
| **A** | *(aucun)* : le code en prod, remesuré | — |
| **E** | `Cette fois, ta question ` | `Cette fois, ta question, toujours au VOUVOIEMENT, ` |
| **F** | `⚠️ Et ta phrase doit CLAQUER` | `Tes deux phrases vouvoient le chat, sans exception. ⚠️ Et ta phrase doit CLAQUER` |

- **E** met le vouvoiement **dans** la phrase de type. Vérifié : `Cette fois, ta question `
  est le début commun des trois phrases de type, et chaque instruction n'en contient
  qu'une.
- **F** ajoute une phrase **juste après** la phrase de type. Vérifié : `⚠️ Et ta phrase
  doit CLAQUER` n'apparaît qu'une fois (`dispatch.py` l.1234).
- ⚠️ Dans les deux cas, **aucun exemple de tournure** (« Venez », « votre ») : une formule
  nommée devient un tic.

Sorties brutes : `suite8ter_raw_{A,E,F}.txt`.

**À compter sur CHAQUE série, en lisant les phrases** (pas la ligne `ouvertures` de la
sonde, qui compte sur 3 mots) :

| critère | seuil pour livrer |
|---|---|
| **tutoiement** (définition du constat) | **≤ 1/18** |
| **tu et vous mélangés dans une même phrase** | **0** |
| « Combien » au premier mot | ≤ 7/18 (ne pas perdre le gain de SUITE 8-bis) |
| premier mot le plus fréquent | ≤ 7/18 |
| invitation finale qui nomme Discord | ≥ 16/18 |
| soudure (« avant de venir… » dans une seule phrase) | ≤ 2/18 |
| question de moins de 80 car., finie par `?` | ≥ la valeur de A |
| pique sur le chat | 0 |
| partie en cours (« aujourd'hui », « ce soir »…) ou Discord inventé | 0 |
| même invitation mot pour mot | ≤ 6/18 |
| replis sur le gabarit fixe **hors 429** | ≤ la valeur de A + 1 |
| longueur médiane (sans le lien) | ≤ 130 car. |

⚠️ Si un 429 retire plus d'une phrase à une série, relancer la série seule après une
minute. Sinon, compter sur les phrases présentes et l'écrire (« 8/17 »).

⚠️ **Plancher de bruit** : jusqu'à 6/18 d'écart sur un compte entre deux passes
identiques. A doit retrouver l'ordre de grandeur du contrôle (≈ 8/18). **Si A mesure moins
de 4/18 de tutoiement, s'arrêter et rendre le tableau** : le défaut n'est alors pas assez
stable pour juger E et F.

# LOT 2 — Décider

- **E ou F passe TOUS les seuils** → LOT 3 avec celle-ci. Si les deux passent : celle qui a
  le moins de tutoiement ; à égalité, **E** (pas de phrase en plus).
- **Aucune ne passe** → **ne rien livrer**, rendre le tableau complet et les sorties
  brutes. SUITE 8-bis reste en prod (décision d'Ahmed).
- **Un seuil autre que le tutoiement échoue de peu** (un seul critère, d'une phrase) →
  **[Ahmed]** décide avant le LOT 3. Ne pas décider à sa place.

# LOT 3 — Livrer (seulement si le LOT 2 l'autorise)

**Si E** : dans `TYPES_DE_QUESTION_JEU_PAR_BOT["sugar"]` (`dispatch.py` l.887–893),
remplacer dans **chacune des trois** phrases `Cette fois, ta question ` par
`Cette fois, ta question, toujours au VOUVOIEMENT, `. Rien d'autre.

**Si F** : dans `_generate_link_line`, la ligne `instruction += phrase_type + " "`
(l.1232) devient `instruction += phrase_type + " " + VOUVOIEMENT_APRES_LE_TYPE`, avec une
constante de classe `VOUVOIEMENT_APRES_LE_TYPE = "Tes deux phrases vouvoient le chat, sans
exception. "` déclarée sous `TYPES_DE_QUESTION_JEU_PAR_BOT`. ⚠️ **Ne pas toucher à la ligne
`⚠️ Et ta phrase doit CLAQUER`** : elle est commune aux six bots. Le `--remplace` de la
mesure produit exactement la même instruction pour Sugar, mais la livraison doit rester
réservée à Sugar.

**Dans les deux cas** :
1. Compléter le commentaire `⚠️ SUITE 8-bis` (l.878) avec une ligne `SUITE 8-ter
   (2026-09-27)` et le tableau A / E / F **complet**, y compris ce qui échoue.
2. **Test** dans `tests/test_phrase_de_lien_jeu_en_cours.py` :
   `test_sugar_rappelle_le_vouvoiement_avec_chaque_type` : pour chaque type (fixer
   `bot._rang_type_question`, vider `bot._link_lines_cache` entre les appels), l'instruction
   capturée contient `VOUVOIEMENT` (E) ou `VOUVOIEMENT_APRES_LE_TYPE` (F) **après** la
   phrase de type. Vérifier aussi que l'instruction de `johnny` avec jeu **ne contient
   pas** ce rappel.
3. Les tests de SUITE 8-bis doivent passer. S'ils comparent le texte exact des phrases de
   type (E les modifie), mettre à jour la valeur attendue, **pas** la logique du test.
   Le verrou anti-mots-interrogatifs doit toujours passer.
4. `python -m pyflakes shared/twitch/dispatch.py tests/test_phrase_de_lien_jeu_en_cours.py`,
   pytest ciblé, puis la suite complète (**jamais deux pytest en parallèle**, port 8599).

# LOT 4 — Contrôler le code livré, puis pousser

1. **Passe de contrôle sans `--remplace`**, sur le code modifié : mêmes options, `--n 18`.
   Sortie : `suite8ter_raw_controle.txt`. **Tous les critères du LOT 1**, rendus ligne par
   ligne. Si le tutoiement dépasse 1/18 ou si un mélange tu/vous apparaît, **ne pas
   commiter** : rendre le tableau.
2. Commit `fix(twitch): rappeler le vouvoiement a Sugar avec le type de question (SUITE 8-ter)`,
   avec les tableaux du LOT 1 et du contrôle **complets** dans le message, et la correction
   du message de `57c78c8` : les replis de la prod SUITE 8 A étaient **2/18**, pas 0/16.
   Push, **`gh run list` jusqu'au vert**.
3. `docker restart bot-sugar` **hors live**. Vérifier :
   `MSYS_NO_PATHCONV=1 docker exec bot-sugar grep -c "VOUVOIEMENT" /app/shared/twitch/dispatch.py`
   (≥ 1), et `docker logs --since 5m bot-sugar` sans erreur.

**Critère de clôture** : tableau complet rendu ; si livraison, CI verte et conteneur
redémarré sans erreur. En live, **[Ahmed]** ou Claude recompte sur les 10 prochains
`!discord` de Sugar : tutoiement, premier mot, et type (visible dans le journal).

---

## Hors périmètre (noté, NON planifié)

- **Type `designer`** : 5/6 de ses questions commencent par « Quel/Quelle ». La rotation
  le dilue (1 tour sur 3), à surveiller seulement.
- **Questions de plus de 80 caractères** : « quel est ton favori dans Kingdom Come:
  Deliverance II ? » recopie le titre complet. Mesuré ici, pas corrigé.
- **La sonde compte les ouvertures sur 3 mots** et n'affiche pas le type de chaque phrase.
  Une ligne « premier mot » et le type dans `tools/sonde_phrase_de_lien.py`, dans un autre
  plan.
- **Johnny, dates inventées** et **Alfred, boisson inventée** : inchangés, rien à faire.
