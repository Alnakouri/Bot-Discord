# PLAN — SUITE 9 : la sonde compte elle-même ce qui se compte

Rédaction : Claude, le **2026-09-27**. Exécution : **Antigravity**. Plan précédent
(SUITE 8-ter, livré `da71b62`) lisible dans git (`53eb0c5:PLAN.md`).

Un seul fichier d'outil : `tools/sonde_phrase_de_lien.py`, plus un fichier de test neuf.
**Aucun appel API, aucun redémarrage, aucun code de prod touché.**

---

## POURQUOI

Le 27/09, trois défauts ont été vus en RECOMPTANT À LA MAIN les sorties brutes, jamais
par la sonde :

- **« Combien » à 17/17** : la sonde affichait « 9× combien de fois », parce qu'elle
  compte les ouvertures sur **trois** mots (`resumer`, l.223).
- **Tutoiement à 8/18** (SUITE 8-bis) : la sonde ne le compte pas. Le compte rendu a dit
  « tous les critères passent ».
- **Questions de moins de 80 caractères, 8/18 contre 14/17** (SUITE 8-ter) : la sonde ne
  le compte pas, et le compte rendu ne l'a pas mentionné.

Chaque plan réécrit des critères que chaque exécution recompte à sa façon, et en oublie
un. Ce qui se compte **mécaniquement** doit être imprimé par la sonde, avec une définition
écrite une fois. Ce qui se **lit** (pique, soudure, partie en cours, objet inventé) reste
à la lecture, comme la docstring de la sonde le dit déjà (l.16–19).

---

# LOT 1 — Une fonction pure `compter(phrases)`

**Fichier** : `tools/sonde_phrase_de_lien.py`, au-dessus de `resumer` (l.210).

`compter(phrases: list[str]) -> dict`, **sans effet de bord**, avec ces définitions
**exactes** (elles ont été prototypées sur les sorties du 27/09 et redonnent les comptes
à la main, cf. LOT 4) :

```python
_TU = re.compile(r"\b(?:tu|te|toi|ton|ta|tes|viens)\b|\bt['’]", re.I)
_EXPRESSIONS_FIGEES = re.compile(r"en veux-tu en voil[àa]", re.I)
_VOUS = re.compile(r"\b(?:vous|votre|vos|venez|rejoignez|passez)\b", re.I)
```

| clé | définition |
|---|---|
| `n` | nombre de phrases |
| `premiers_mots` | `Counter` du premier mot : `re.match(r"\W*(\w+)", p)`, en minuscules |
| `tutoiement` | phrases où `_TU` trouve un mot **après** avoir retiré `_EXPRESSIONS_FIGEES` |
| `melange` | parmi celles-là, celles où `_VOUS` trouve aussi un mot |
| `questions_courtes` | phrases qui contiennent un `?` **et** dont le texte avant le premier `?`, `strip()`é, fait **moins de 80** caractères. Une phrase sans `?` ne compte pas. |
| `meme_question` | le plus grand nombre de phrases ayant **exactement** le même texte avant le premier `?` (0 si aucune question) |
| `meme_invitation` | `(texte, nombre)` le plus fréquent de l'**invitation normalisée** : ce qui suit le premier `?` (ou toute la phrase s'il n'y en a pas), où tout caractère hors `[\w\s'’-]` devient une espace (emoji, ponctuation), puis minuscules et espaces réduites |
| `discord` | phrases contenant `discord`, insensible à la casse |

⚠️ **Ces critères ne jugent rien.** Le tutoiement n'est une faute que chez un bot qui
vouvoie : Johnny a le droit de tutoyer (`CLAUSES_FORME_JEU_PAR_BOT["johnny"]` : « Tutoie
ou vouvoie, mais la même personne »). La sonde **imprime** le compte, le lecteur juge
selon le bot.

⚠️ Importer `re` et `collections` en tête de fichier s'ils n'y sont pas.

# LOT 2 — L'afficher, et le type de chaque phrase

1. **`resumer`** (l.210) appelle `compter` et ajoute ces lignes, **sans retirer** les
   lignes existantes (d'autres plans lisent `ouvertures`) :

   ```
     premier mot       : 7x « combien », 4x « entre », 4x « bohemia »      (les 3 plus frequents)
     tutoiement        : 8/18   (dont 2 melanges tu/vous dans la meme phrase)
     questions < 80 car: 11/18  (texte avant le premier « ? »)
     meme question     : 1x au plus
     meme invitation   : 2x « venez en discuter sur discord »
     nomme Discord     : 18/18
   ```

   Les dénominateurs sont le nombre de phrases **exploitables** (`n` de `compter`), pas
   `args.n`.

2. **Le type de question** : la prod l'écrit dans son journal depuis SUITE 8-bis
   (`✨ … (type : choix) écrite par le bot : …`, `dispatch.py` l.1278). Dans la boucle de
   `main` (l.350), après la génération, chercher dans `f._journal` le motif
   `r"\(type : (\w+)\)"`. S'il y est, imprimer la ligne sous la forme
   `  3. [ 2.41s] (choix) La phrase…` ; sinon la ligne ne change pas. Garder le type de
   chaque phrase exploitable dans une liste parallèle à `phrases`.
3. **Si au moins un type a été vu**, `resumer` ajoute une ligne par type :
   `  type choix       : 6 phrases ; premier mot 4x « entre »`.

# LOT 3 — Relire une sortie existante : `--relire FICHIER`

Nouvelle option. Avec elle, la sonde **n'appelle rien** : ni `charger` (donc aucun `.env`
lu), ni modèle. Elle lit le fichier, en extrait les phrases, et appelle `resumer`.

- Placement : dans `main`, **juste après** `sys.stdout.reconfigure(...)` (l.282) et
  **avant** tout le reste, avec un `return 0`.
- Format lu, celui que la sonde imprime elle-même :
  `^\s*\d+\.\s+\[[^\]]*\]\s+(?:\((\w+)\)\s+)?(.*\S)\s*$`. Groupe 1 = le type s'il y en a un,
  groupe 2 = la phrase. Une phrase qui commence par `<<` (`<<repli sur le gabarit fixe>>`,
  `<<EXCEPTION …>>`) compte comme un **repli**, pas comme une phrase. Toute autre ligne
  (en-tête, `↳ brut`, résumé, STDERR) est ignorée.
- Ajouter l'option à la docstring (l.27–65), dans le style des autres : ce qu'elle a servi
  à trancher, soit « recompter SUITE 5 à 8-ter sans rappeler le modèle ».

# LOT 4 — Vérifier sur les sorties du 27/09 (hors pytest)

Lancer `--relire` sur ces fichiers et comparer à ce tableau, **à l'unité près**. Tout
écart = une définition mal recopiée : corriger le code, pas le tableau.

`B = ~/.gemini/antigravity-cli/brain`

| fichier | n | replis | 1er mot | tutoiement / mélange | questions < 80 | même question | même invitation | Discord |
|---|---|---|---|---|---|---|---|---|
| `B/601962eb-…/scratch/suite5_raw_B2.txt` | 17 | 1 | combien 17 | 0 / 0 | 15 | 2 | venez en discuter sur discord 4 | 17 |
| `B/221acb3a-…/scratch/suite8_raw_A.txt` | 16 | 2 | combien 16 | 0 / 0 | 13 | 3 | venez en discuter sur discord 8 | 16 |
| `B/221acb3a-…/scratch/suite8bis_raw_controle.txt` | 18 | 0 | combien 7 | 8 / 2 | 11 | 1 | venez en discuter sur discord 2 | 18 |
| `B/221acb3a-…/scratch/suite8ter_raw_A.txt` | 17 | 1 | combien 6 | 3 / 3 | 14 | 1 | venez en discuter sur discord 2 | 17 |
| `B/221acb3a-…/scratch/suite8ter_raw_E.txt` | 18 | 0 | entre 9 | 0 / 0 | 8 | 1 | venez nous raconter vos exploits sur discord 4 | 18 |
| `B/221acb3a-…/scratch/suite8ter_raw_controle.txt` | 16 | 2 | entre 8 | 0 / 0 | 11 | 2 | venez en discuter sur discord 3 | 16 |

Coller la sortie de ces six `--relire` dans le compte rendu.

# LOT 5 — Le test

**Fichier neuf** : `tests/test_sonde_compte_les_criteres.py`. Import comme les tests
existants : `from tools.sonde_phrase_de_lien import compter` (voir
`tests/test_phrase_de_lien_jeu_en_cours.py` l.357).

⚠️ **Aucune lecture des fichiers du scratch** : ils ne sont pas dans le dépôt et la CI ne
les a pas ([[feedback-le-local-ment-sans-cles]]). Les phrases sont **recopiées dans le
test**, mot pour mot, depuis les sorties du 27/09 :
(les « » ci-dessous DÉLIMITENT la phrase dans ce plan : ils ne font pas partie de la
chaîne Python)

- `« Combien d'épées rouillées ton forgeron a-t-il déjà pliées en deux en Bohême ? Venez nous raconter vos pires ratés sur Discord ! ✨ »` → tutoiement **et** mélange.
- `« Bohemia vous a fait suer sang et eau ou juste baver sur votre écran ? Viens en débattre sur Discord. ✨ »` → tutoiement **et** mélange.
- `« Entre épées, châteaux de Bohême et boue en veux-tu en voilà, quel est votre personnage ou lieu préféré dans ce jeu ? Venez tout nous raconter sur Discord ! ✨ »` → **ni** tutoiement **ni** mélange (expression figée).
- `« Combien d'heures perdues dans la boue de cette Bohême médiévale ? Viens nous raconter tes misères sur Discord ✨ »` → tutoiement, **pas** de mélange.
- `« Combien de têtes de bandits avez-vous croisées en Bohême ? Venez en discuter sur Discord ! ✨ »` et la même avec `🍬` à la place de `✨` → `meme_question == 2` et `meme_invitation == ("venez en discuter sur discord", 2)` : l'emoji ne compte pas.
- Une phrase sans `?` → ne compte pas dans `questions_courtes`.
- `premiers_mots` : `« Entre nous, quel est… »` donne `entre`.

Et un test de `--relire` sur un **petit fichier écrit par le test** dans `tmp_path`
(trois lignes au format de la sonde, dont une `<<repli sur le gabarit fixe>>` et une avec
`(choix)`), qui vérifie que la sonde rend 2 phrases, 1 repli et le type `choix`, **sans
appeler** `charger` (le remplacer par une fonction qui lève, pour le prouver).

# LOT 6 — Livrer

1. `python -m pyflakes tools/sonde_phrase_de_lien.py tests/test_sonde_compte_les_criteres.py`
2. pytest : le nouveau fichier et `tests/test_phrase_de_lien_jeu_en_cours.py` (qui importe
   déjà la sonde), puis la suite complète (**jamais deux pytest en parallèle**, port 8599).
3. Commit `feat(tools): la sonde de phrase de lien compte premier mot, tutoiement, questions et redites (SUITE 9)`,
   avec le tableau du LOT 4 **tel que la sonde l'a rendu**. Push, **`gh run list` jusqu'au
   vert**.
4. **Pas de redémarrage** : aucun conteneur n'exécute la sonde.

**Critère de clôture** : les six `--relire` redonnent le tableau du LOT 4 à l'unité près,
tests et CI verts.

---

## Hors périmètre (noté, NON planifié)

- **Sugar en live** : recompter « Entre », la longueur des questions et le vouvoiement sur
  les 10 prochains `!discord` (le journal donne le type). Rien à faire avant.
- **Faire lire les critères de chaque plan par la sonde** (seuils en option) : non. La
  sonde compte ; le plan fixe les seuils ; le lecteur compare.
- **Johnny, dates inventées** et **Alfred, boisson inventée** : inchangés.
