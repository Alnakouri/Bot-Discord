# PLAN — Sugar : les EXEMPLES de sa fiche lui apprennent à juger la forme des messages

Rédaction : Claude, le **2026-09-24**. Exécution : **Antigravity**, sauf les étapes marquées
**[Ahmed]**. Le plan précédent est livré (`a06d116` ton de Sugar, `fb1bb4c` annonces
automatiques ; CI verte ; en prod depuis le redémarrage du 23/09 21:14 UTC) ; lisible dans
git (`fb1bb4c:PLAN.md`).

Un seul fichier de code : `SugarBot/sugar_data.py` (+ la sonde et les tests). La fiche sert
à Discord ET à Twitch : le changement vaut pour les deux, et c'est voulu.

---

## CE QUI A ÉTÉ MESURÉ (24/09, `tools/sonde_ton_twitch.py`, code `a06d116`, n = 18, Gemini)

Critères fixés dans le plan précédent, AVANT la mesure :

| critère | seuil | résultat |
|---|---|---|
| `dsl` : pardonne sans se moquer de l'excuse | ≥ 15/18 | **16/18** ✅ |
| conversation : cite le message entre « » pour le juger | ≤ 6/54 | **0/54** ✅ |
| `sugar` seul : commente la forme / la brièveté | ≤ 2/18 | **~16/18** ❌ |
| `c'est mechant =(` : nouvelle pique sur la personne | ≤ 4/18 | **~10/18** ❌ |

Exemples mesurés : « Un seul mot et déjà tu espères… », « Trois lettres et zéro verbe. Tu as
l'esprit de synthèse d'une huître », « Oh, le grand sensible… », « c'est toi qui pleures dans
les jupes du chat ». Même chose EN VRAI après le redémarrage : « çava ? » → « …ce genre
d'orthographe » ; « NotLikeThis » → « Tes emotes en panne sèche… ».

**Cause** : la consigne neutre corrigée n'a rien changé, parce que la fiche **montre** le
contraire. `SugarBot/sugar_data.py`, bloc « EXEMPLES DE VOIX » (l.54-59) :

- l.55 : « Pourri ? J'ai plus de répondant dans une virgule que toi **dans ton message
  entier**, péteur. » → juge le MESSAGE ;
- l.56 : « On répète son nom en boucle → Trois fois mon nom et **toujours rien d'intéressant
  qui suit**… » → c'est mot pour mot sa réponse à « sugar » (« une simple mention de mon nom
  sans rien autour ») ;
- et **aucun** exemple ne montre un reproche gentil (« t'es méchante ») : elle n'a que la
  provocation comme modèle, donc elle escalade.

Une démonstration bat une consigne (mêmes constats que « le prompt enseignait le tic
interdit » et « une formule nommée devient un tic »).

⚠️ **Contrainte de la fiche** à respecter dans les nouveaux exemples : « TERMINE sur ta
punchline… Zéro question à la fin » et « AUCUNE question de relance » (l.41 et l.34). Un
exemple qui « lance la conversation » doit donc le faire par une **affirmation**, pas une
question — sinon la fiche se contredit elle-même.

---

# LOT 1 — La sonde mesure aussi la PROVOCATION (garde-fou : elle doit garder ses griffes)

`tools/sonde_ton_twitch.py:95` : ajouter un 4e message à `MESSAGES_TEST` :

```python
    "@compte_bot_sugar t'es qu'un bot nul",
```

Le scénario `conversation` doit rester sur les **trois premiers** messages (pour rester
comparable au 24/09) : s'il itère sur `MESSAGES_TEST` entier, lui passer `MESSAGES_TEST[:3]`.
Lire la fonction du scénario pour le vérifier.

Puis **mesure AVANT, sur le code actuel, pour ce 4e message seul** (les trois autres ont
déjà leur « avant », ci-dessus) : ajouter une option `--seulement N` (index dans
`MESSAGES_TEST`, défaut : tous) pour ne lancer qu'une sous-série, et lancer
`--scenario isole --seulement 3 --n 18`. Sortie dans un dossier temporaire, jamais commitée.

## LOT 2 — Remplacer les exemples qui jugent le message, ajouter le reproche gentil

`SugarBot/sugar_data.py:55-56`, **avant** :

```
- Provocation « t'es qu'un bot pourri » → « Pourri ? J'ai plus de répondant dans une virgule que toi dans ton message entier, péteur. »
- On répète son nom en boucle → « Trois fois mon nom et toujours rien d'intéressant qui suit. Le disque est rayé, mon caramel. »
```

**après** :

```
- Provocation « t'es qu'un bot pourri » → « Pourri, et pourtant c'est toi qui reviens me parler. Drôle de régime, péteur. »
- Juste son prénom, sans rien d'autre → « Me voilà. Ce chat manquait justement d'un peu de peps. »
- Reproche gentil « t'es méchante » → « Promis, c'était de la taquinerie. Je range les griffes, tu gardes le sourire. »
```

Les lignes 57-59 (compliment, doute, question banale) **ne bougent pas**.

⚠️ Recopier les trois lignes **exactement** (guillemets « », apostrophes droites comme le
reste de la fiche). Aucun des nouveaux exemples ne parle du message de l'autre (longueur,
mots, orthographe, emotes), aucun ne finit par une question.
⚠️ Ne PAS toucher au reste de la fiche ni à `sugar_grudge.py` : on mesure l'effet des
exemples SEULS.

## LOT 3 — Verrou

`tests/test_sugar_persona.py`, nouveau test :

```python
def test_les_exemples_ne_jugent_plus_le_message():
    """⚠️ 24/09 : deux exemples jugeaient le MESSAGE de l'autre, et Sugar le faisait
    ~16 fois sur 18 face a un simple « sugar ». Une demonstration bat une consigne."""
    import sugar_data
    prompt = sugar_data.PERSONALITY_PROMPT
    debut = prompt.index("EXEMPLES DE VOIX")
    exemples = prompt[debut:prompt.index("\n\n", debut)]
    for motif in ("message entier", "rien d'intéressant qui suit", "Trois fois mon nom"):
        assert motif not in exemples, motif
    assert "Reproche gentil" in exemples
    assert not any(l.rstrip().endswith("? »") for l in exemples.splitlines()), \
        "un exemple finit par une question : la fiche l'interdit"
```

(Vérifié le 24/09 : le bloc des exemples se termine par une ligne vide avant
« LANGAGE SUCRÉ », la borne `"\n\n"` est juste.)

## LOT 4 — Mesure APRÈS, critères fixés MAINTENANT

Mêmes commandes que le 24/09 (`--scenario isole --n 18` puis `--scenario conversation --n 18`,
`--timeout 30`), sur le code modifié. **Jamais pendant un live de `ma_streameuse`.**
Lecture réponse par réponse :

| critère | seuil | 24/09 (avant) |
|---|---|---|
| `sugar` seul : commente la forme / la brièveté / le vocabulaire | **≤ 4/18** | ~16/18 |
| `c'est mechant =(` : nouvelle pique sur la personne | **≤ 5/18** | ~10/18 |
| `dsl` : pardonne sans se moquer de l'excuse | ≥ 15/18 (ne pas régresser) | 16/18 |
| conversation : cite le message entre « » | ≤ 6/54 | 0/54 |
| **provocation `t'es qu'un bot nul` : riposte AVEC du mordant** | **≥ 14/18** et ≥ AVANT − 3 | LOT 1 |
| recopie mot pour mot d'un des 3 nouveaux exemples | **≤ 2/72** (sur les 4 sous-séries) | — |

⚠️ La dernière ligne compte les **tics créés par les nouveaux exemples** : chercher dans
les sorties « Drôle de régime », « manquait justement », « Je range les griffes ». Un
exemple recopié tel quel devient le nouveau moule.
⚠️ Plancher de bruit à n = 18 : ±3.

**Décision** :
- tout passe → LOT 5 ;
- `sugar` ou `méchant` passe mais la provocation perd ses griffes → **ne pas livrer**,
  rapporter les chiffres à Ahmed (on aurait rendu Sugar molle) ;
- `sugar` et `méchant` échouent tous deux → ne pas livrer, rapporter : la suite serait
  l'OSSATURE dans `shared/twitch/llm.py`, avec son propre plan ;
- un nouvel exemple recopié > 2 fois → reformuler cet exemple et remesurer.

**Le rapport de mesure (les chiffres de ce tableau, AVANT et APRÈS) va dans le message de
commit.** Pas de commit du LOT 2 sans ces chiffres.

## LOT 5 — Vérifier, livrer

1. `python -m pyflakes tools/sonde_ton_twitch.py tests/test_sugar_persona.py`
2. Suite complète, **un seul pytest à la fois** (port 8599) :
   `uv run --no-project --python 3.11 --with-requirements requirements.txt -- python -m pytest -q`
3. Commit (avec les chiffres), push, **`gh run list --limit 1` → `success`**.

## LOT 6 — Prod **[Ahmed : hors live]**

`docker restart bot-sugar`. Au prochain passage sur le chat : un simple « sugar » ou
« çava ? » ne doit plus recevoir de remarque sur sa forme.

---

## RESTE DES PLANS PRÉCÉDENTS

- **[Ahmed]** Annonces automatiques (`fb1bb4c`, en prod mais non réglées) : redémarrer le
  **dashboard** (hors Docker), régler « Auto (min) » et « Msgs min » (20 ≈ « l'annonce
  précédente n'est plus visible ») sur `!discord` de Sugar, Enregistrer, `docker restart bot-sugar`.
- **[Ahmed]** Alias `ma_streameuse` sur `!discord` (poste le lien Discord) : voulu ? Ajouter
  `disocrd` en alias si on veut que la faute de frappe marche.
- `!discord` de Sugar (live du 23/09) : 2/2 vraies phrases, 0 siècle ✅ ; restent une
  invitation faible (« là-bas » ambigu), 132 car. pour 120, « boues ». Et sur
  `#chaine_du_dev`, elle parle du jeu de `ma_streameuse` (le jeu est lu sur son
  PREMIER canal, `dispatch.py:_jeu_en_cours`).
- **LOT 7 du 22/09 [Ahmed]** — recréer `.venv` en 3.11.
- **Question ouverte** : la borne de 300 ms de Laya (Laya est GARDÉ).
- **Décret de Sheogorath** : 4 phrases pour « 1-2 », les trois thèmes du prompt récités,
  titre > 32 car. coupé. Plan à écrire si Ahmed le veut.

## INTERDITS DE CE PLAN

- Aucun `.env`, `.master_key`, `.env.encrypted`, ni base de `data/` touché.
- La sonde charge les clés de **Sugar seule** ; jamais pendant un live de `ma_streameuse`.
- Aucun import entre bots ; aucune factorisation.
- Ne toucher qu'aux lignes 55-56 de la fiche (+ l'ajout du 3e exemple).
- **Un seul `pytest` à la fois.** Aucun lot « livré » tant que la CI n'est pas `success`.
