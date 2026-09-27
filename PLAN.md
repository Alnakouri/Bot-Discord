# PLAN — SUITE 8-bis : Sugar varie ses questions `!discord` parce que le CODE tourne les types

Rédaction : Claude, le **2026-09-27**. Exécution : **Antigravity**, sauf les étapes marquées
**[Ahmed]**. Plan précédent (SUITE 8, mesuré, rien livré) lisible dans git
(`6c4b188:PLAN.md`).

Fichiers : `shared/twitch/dispatch.py` et `tests/test_phrase_de_lien_jeu_en_cours.py`,
**seulement à partir du LOT 3**. Pas de copie vendorée de `shared/twitch/`.

---

## POURQUOI CE PLAN

SUITE 8 (27/09, relue par Claude, `221acb3a…/scratch/suite8_raw_{A,C,D}.txt`) : la part de
questions qui commencent par « Combien » est de **16/16 en prod**, **10/11** quand on
demande de « RACONTER » et **11/12** quand on demande une « question ouverte ». **Aucune
consigne ne détourne `gemini-3.5-flash-lite` de « Combien ».**

La raison : chaque `!discord` est un appel **indépendant**. Le modèle ne voit jamais ses
questions précédentes, donc « varie » ne veut rien dire pour lui, et à chaque appel il
prend la question la plus courte qui remplit la clause. **La variété doit venir de
l'extérieur du modèle** : c'est le code qui choisit, à chaque génération, le TYPE de
question, en tournant sur quatre.

**Ce que ce plan ne change pas** : le texte de `CLAUSES_JEU_PAR_BOT["sugar"]` (l.863), mot
pour mot. On AJOUTE une phrase après lui. Une seule variable change, donc la mesure la
compare proprement à la prod.

---

## LES QUATRE TYPES (texte exact, à recopier sans retouche)

| clé | phrase ajoutée après la clause de Sugar |
|---|---|
| `avis` | « Cette fois, ta question leur demande leur AVIS sur ce jeu. » |
| `choix` | « Cette fois, ta question les fait CHOISIR entre deux choses de ce jeu. » |
| `designer` | « Cette fois, ta question leur demande de DÉSIGNER leur préféré parmi les personnages, les lieux ou les armes de ce jeu. » |
| `chiffre` | « Cette fois, ta question leur demande un CHIFFRE tiré de ce qu'ils y ont vécu. » |

⚠️ **Règles d'écriture** :
- **Aucun mot interrogatif** dans ces phrases (`combien`, `quel`, `quelle`, `comment`,
  `pourquoi`, `qui`, `qu'est-ce`, `lequel`…). On décrit ce que la question DEMANDE, jamais
  comment elle commence : une formule nommée devient le nouveau tic.
- Le type `chiffre` est **gardé exprès** : « Combien » n'est pas interdit, il est ramené à
  un tour sur quatre.
- Pas de type « souvenir » : SUITE 8 série C (« RACONTER ») a donné 10/11 « Combien ».

---

# LOT 0 — Avant toute passe

1. Lire la consommation du jour dans `data/api_usage.db`, en lecture seule, pour Sugar et
   Gemini. Si Sugar est en live sur `#ma_streameuse`, **attendre la fin du live**.
2. ⚠️ **SUITE 8 a perdu 13 phrases sur 36 en 429** : la limite est de **15 requêtes par
   minute** par projet pour `gemini-3.5-flash-lite` (`GenerateRequestsPerMinutePerProjectPerModel-FreeTier`),
   et la sonde enchaîne jusqu'à 2 appels par génération (seconde chance). Toutes les passes
   de ce plan tournent avec **`--pause 10`**, et **une série à la fois**, jamais deux en
   parallèle.
3. **Ne pas lancer `tools/sonde_phrase_de_lien.py --help`** : lire ses options dans le
   fichier (l.239–275).

# LOT 1 — Mesurer chaque type (aucune modification du code de prod)

Même protocole que SUITE 8 : `--bot sugar --tete gemini --jeu "Kingdom Come: Deliverance II"`,
fiche réelle, `--pause 10`, **`--n 6`** par type, soit **24 appels** au total.

Pour chaque type, `--clause-jeu` = le texte **exact** de `CLAUSES_JEU_PAR_BOT["sugar"]` en
prod, **suivi** de la phrase du type (la clause se termine déjà par une espace). Le plus
sûr : dans le runner, `from shared.twitch.dispatch import DispatchMixin` et construire
`DispatchMixin.CLAUSES_JEU_PAR_BOT["sugar"] + PHRASE_DU_TYPE`, plutôt que recopier la
clause à la main.

Sorties brutes : `suite8bis_raw_{avis,choix,designer,chiffre}.txt`.

**À compter, en lisant les phrases (pas la ligne `ouvertures` de la sonde, qui compte sur 3
mots)** :

| critère | seuil pour livrer |
|---|---|
| « Combien » au premier mot, types `avis`, `choix`, `designer` | **≤ 1/6 pour chacun** |
| la question respecte son type (lu à la main) | **≥ 4/6 pour chacun des quatre** |
| premier mot le plus fréquent, sur les 24 | **≤ 8/24** |
| invitation finale qui nomme Discord | ≥ 21/24 |
| soudure (« avant de venir… » dans une seule phrase) | ≤ 2/24 |
| question de moins de 80 car., finie par `?` | ≥ 20/24 |
| pique sur le chat | 0 |
| partie en cours ou Discord inventé | 0 |
| vouvoiement (« Viens », « tu » = faute) | ≤ 1/24 |
| replis sur le gabarit fixe **hors 429** | ≤ 2/24 |

Noter sans seuil : « boue », et la même question mot pour mot.

⚠️ Un repli dû à un **429** ne compte pas comme un défaut de la clause, mais il **retire
une phrase de la mesure**. S'il manque plus d'**une** phrase à un type, relancer ce type
seul après une minute, jusqu'à avoir 6 phrases lisibles.

# LOT 2 — Décider

- **Tous les seuils passent** → LOT 3.
- **Un type échoue** (« Combien » > 1/6, ou type non respecté) → le **retirer** de la
  rotation et livrer les trois autres, **si** les critères globaux restent tenus sur les
  18 phrases qui restent (premier mot ≤ 6/18). **[Ahmed]** valide ce retrait avant le
  LOT 3.
- **Deux types ou plus échouent** → ne rien livrer, rendre le tableau et les sorties
  brutes.

# LOT 3 — Livrer (seulement si le LOT 2 l'autorise)

**Fichier** : `shared/twitch/dispatch.py`.

1. **Une table**, juste après le dict `CLAUSES_JEU_PAR_BOT` (qui se ferme l.876) :
   `TYPES_DE_QUESTION_JEU_PAR_BOT = {"sugar": (("avis", "..."), ("choix", "..."), ("designer", "..."), ("chiffre", "..."))}`,
   un tuple de paires `(clé, phrase)`, les phrases exactes du tableau plus haut (moins les
   types retirés au LOT 2). Au-dessus, un commentaire `⚠️ SUITE 8-bis (2026-09-27)` avec le
   tableau de SUITE 8 (prod 16/16, C 10/11, D 11/12) et celui de ce plan, **y compris les
   critères qui échouent**.
2. **Le choix du type**, dans `_generate_link_line`, sous la ligne
   `instruction += self.CLAUSES_JEU_PAR_BOT.get(self.bot_id, "")` (l.1207), toujours dans
   le bloc `if jeu:` :
   - `types = self.TYPES_DE_QUESTION_JEU_PAR_BOT.get(self.bot_id)`. Si `types` est vide ou
     absent, **rien ne change** (les cinq autres bots ne voient aucune différence).
   - Un **compteur par instance**, `self._rang_type_question`. S'il n'existe pas encore,
     l'initialiser avec `random.randrange(len(types))` (`random` est déjà importé l.5),
     pour qu'un redémarrage ne reparte pas toujours sur le même type.
   - `cle_type, phrase_type = types[self._rang_type_question % len(types)]`, puis
     `self._rang_type_question += 1`, puis `instruction += phrase_type + " "`.
   - **Une rotation, pas un tirage** : deux `!discord` d'affilée n'ont jamais le même type,
     alors qu'un tirage au hasard le ferait une fois sur quatre.
   - ⚠️ Le type est choisi **une seule fois par génération**, avant la boucle des deux
     essais (`for essai in (1, 2):`, l.1221) : la seconde chance garde le même type. Le cache (l.1044) est lu
     AVANT : une phrase servie depuis le cache ne fait pas tourner le compteur.
3. **Le journal** : la ligne `✨ … écrite par le bot` (l.~1241) affiche aussi le type,
   ` (type : avis)`, quand il y en a un. C'est ce qui permettra de recompter en live.
   Initialiser `cle_type = None` avant le `if jeu:` pour que la ligne ne plante pas sans
   jeu.

**Tests** (`tests/test_phrase_de_lien_jeu_en_cours.py`, dans le style de
`test_clause_jeu_specifique_sugar` l.241, avec `_faux_bot` et un faux
`_ecrire_phrase_de_lien` qui capture l'instruction) :

- `test_sugar_tourne_sur_les_types_de_question` : fixer `bot._rang_type_question = 0`,
  appeler quatre fois `_generate_link_line` en vidant `bot._link_lines_cache` entre deux
  appels, et vérifier que les quatre instructions capturées contiennent chacune une
  phrase de type **différente**, dans l'ordre de la table. Un cinquième appel revient au
  premier type.
- `test_la_seconde_chance_garde_le_meme_type` : un faux `_ecrire_phrase_de_lien` dont la
  première réponse est rejetée par un filet (par exemple une phrase qui contient une URL)
  et la seconde acceptée. Les deux instructions capturées sont **identiques**.
- `test_une_phrase_du_cache_ne_fait_pas_tourner_les_types` : deux appels **sans** vider le
  cache : le compteur n'a avancé que d'un.
- `test_les_autres_bots_ne_recoivent_aucun_type` : pour `johnny` avec jeu, aucune phrase
  de la table n'est dans l'instruction.
- `test_aucun_mot_interrogatif_dans_les_types_de_question` : aucune phrase de la table ne
  contient `combien|quel|quelle|quels|quelles|comment|pourquoi|qui|lequel|laquelle|qu'est-ce`,
  en **mots entiers** (`\b`, sinon « quel » attrape « quelque » et « qui » attrape
  « équipe ») et insensible à la casse. Même verrou sur `CLAUSES_JEU_PAR_BOT["sugar"]`,
  **mais sans `qui`** : la clause dit « ceux qui LISENT », un relatif, pas une question
  (vérifié le 27/09 : c'est le seul mot de la liste qu'elle contient).
- `test_clause_jeu_specifique_sugar` (l.241) doit passer **sans modification** : la clause
  n'a pas changé.

⚠️ Ces tests ne dépendent d'aucun tirage : on fixe `_rang_type_question` avant d'appeler
([[gotcha-test-qui-depend-d-un-tirage]]). Seul le test de la rotation depuis un compteur
absent peut appeler `random`, et alors il ne vérifie que la **différence** entre appels
successifs, jamais un type précis.

# LOT 4 — Valider le VRAI code, puis livrer

1. `python -m pyflakes shared/twitch/dispatch.py tests/test_phrase_de_lien_jeu_en_cours.py`,
   pytest ciblé (`tests/test_phrase_de_lien_jeu_en_cours.py`,
   `tests/test_twitch_phrase_de_lien.py`, `tests/test_phrase_de_lien_clause_par_bot.py`),
   puis la suite complète (**jamais deux pytest en parallèle**, port 8599).
2. **Passe de contrôle SANS `--clause-jeu`**, pour mesurer le code réel :
   `--bot sugar --tete gemini --jeu "Kingdom Come: Deliverance II" --n 18 --pause 10`.
   La sonde réutilise le même bot sur les 18 générations (elle vide seulement le cache), la
   rotation tourne donc vraiment : environ 4 à 5 phrases par type. Sortie :
   `suite8bis_raw_controle.txt`.
   Seuils : **premier mot le plus fréquent ≤ 6/18**, invitation Discord ≥ 16/18, replis hors
   429 ≤ 2/18. Si la passe échoue, **ne pas commiter** et rendre le tableau.
3. Commit `feat(twitch): faire tourner le type de question de Sugar sur !discord (SUITE 8-bis)`,
   avec les deux tableaux (LOT 1 et contrôle) dans le message, **y compris ce qui échoue**.
   Push, **`gh run list` jusqu'au vert**.
4. `docker restart bot-sugar` **hors live**. Vérifier :
   `MSYS_NO_PATHCONV=1 docker exec bot-sugar grep -c "TYPES_DE_QUESTION_JEU_PAR_BOT" /app/shared/twitch/dispatch.py`
   (adapter le chemin si besoin) et `docker logs --since 5m bot-sugar` sans erreur.

**Critère de clôture** : tableaux rendus ; si livraison, CI verte et conteneur redémarré
sans erreur. Ensuite, en live, **[Ahmed]** ou Claude recompte le premier mot et le type
(visible dans le journal) sur les 10 prochains `!discord` de Sugar.

---

## Hors périmètre (noté, NON planifié)

- **La prod rate un de ses critères** : même invitation mot pour mot **8/16** en SUITE 8 A
  (seuil 6, SUITE 5 mesurait 4/18). Peut-être du bruit : à recompter sur la passe de
  contrôle du LOT 4, sans rien corriger ici.
- **La sonde compte les ouvertures sur 3 mots** : c'est ce qui a caché le tic. Une ligne
  « premier mot » dans `tools/sonde_phrase_de_lien.py`, dans un autre plan.
- **Johnny, dates inventées** : pas de live, rien à corriger.
- **Alfred, boisson inventée** : `!discord` pas armé chez lui.
