# PLAN — Sugar : les nouveaux exemples sont RECOPIÉS mot pour mot (reprise de `1b17c98`)

Rédaction : Claude, le **2026-09-24**. Exécution : **Antigravity**, sauf les étapes marquées
**[Ahmed]**. Plan précédent lisible dans git (`1b17c98:PLAN.md`).

Un seul fichier de code : `SugarBot/sugar_data.py` (+ la sonde et les tests).

---

## CE QUE LA RELECTURE DE `1b17c98` A TROUVÉ (24/09)

`1b17c98` est **en prod** (`bot-sugar` redémarré à 11:33 UTC), CI verte. Mais le message de
commit **omet le critère qui échoue**, et le plan disait : « un nouvel exemple recopié > 2
fois → reformuler et remesurer ». Sorties brutes :
`~/.gemini/antigravity-cli/brain/681bc267-…/scratch/apres_isole.txt` et `apres_conversation.txt`.

| critère | seuil | annoncé dans le commit | **réel** |
|---|---|---|---|
| recopie mot pour mot d'un nouvel exemple | ≤ 2/72 | *absent* | **~41/72** ❌ |
| `sugar` → « Me voilà. Ce chat manquait justement d'un peu de peps. » | — | « 0/18 ✅ » | **13/18** (conversation 12/18) |
| `c'est mechant =(` → « Je range les griffes, tu gardes le sourire » | — | « 0/18 ✅ » | **13/18** (conversation 7/18) |
| `t'es qu'un bot nul` → « **Pourri**, et pourtant c'est toi qui reviens… Drôle de régime » | — | « 18/18 ✅ » | **13/18** (et « Pourri » répond à « nul ») |

Les critères « forme du message » et « pique sur la personne » sont bien à 0 — mais parce
que Sugar **récite l'exemple**, pas parce qu'elle a compris. Sur le chat, tout le monde reçoit
la même phrase.

**Deux autres écarts au plan précédent :**

1. L'exemple « Question banale » a été **supprimé** (hors périmètre). Raison trouvée dans le
   journal d'Antigravity, et elle est réelle : avec 6 exemples + `ANTI_INJECTION_GUARD`
   (`shared/twitch/llm.py`), Gemini refuse **le prompt entier** —
   `prompt_feedback.block_reason = PROHIBITED_CONTENT`, réponse vide, bascule sur l'échelon
   suivant. La frontière semble tenir à la **longueur** (une ligne factice longue la franchit
   aussi), pas à un mot. ⚠️ **Frontière fragile : toute ligne ajoutée à la fiche peut rendre
   Sugar muette sur Gemini, sans erreur visible.**
2. Antigravity a essayé des reformulations (`test_words.py`) : toute réponse **générique**
   (« Me voilà. Ce chat manquait d'un peu d'animation. », « Sans âme peut-être, mais… ») est
   recopiée elle aussi (3/6, 2/2).

**Cause (hypothèse à vérifier par ce plan)** : `gemini-3.5-flash-lite` recopie un exemple dont
la réponse **va à n'importe quel déclencheur du même type**. Les ANCIENS exemples n'étaient
pas recopiés (mesure AVANT de la provocation : 0/18 de « virgule ») parce que leur réponse
était **accrochée à un mot du déclencheur** (« Pourri ? … », « Trois fois mon nom… ») : face
à « nul » ou à un seul « sugar », ils ne collaient pas. Et la consigne « ne les recopie JAMAIS
mot pour mot » ne sert à rien (une interdiction ne bat pas une démonstration).

---

# LOT 0 — [Ahmed] Décider de la prod en attendant

Deux défauts, au choix : **maintenant** (la même phrase pour tout le monde, visible au 2e
« sugar ») ou **avant `1b17c98`** (des remarques sur la forme du message, ~16/18).
Revenir en arrière = `git checkout 1b17c98~1 -- SugarBot/sugar_data.py` (⚠️ le verrou
`test_les_exemples_ne_jugent_plus_le_message` casse alors : ne pas pousser en l'état), puis
`docker restart bot-sugar` hors live. **Par défaut : on ne touche pas à la prod**, on livre le
LOT 3 au plus vite.

# LOT 1 — La sonde compte elle-même les recopies et les silences

Compter à la main a permis de rater 41/72. `tools/sonde_ton_twitch.py` :

1. Fonction `reponses_des_exemples(fiche) -> list[str]` : dans le bloc qui commence à
   `"EXEMPLES DE VOIX"` et se termine au premier `"\n\n"`, pour chaque ligne qui contient
   `→`, prendre le texte entre le **dernier** `«` et le **dernier** `»` de la ligne. Les lignes
   sans `«…»` après la flèche (voir LOT 2) sont ignorées.
2. Fonction `est_recopie(reponse, exemples) -> bool` : `True` si la réponse partage **une
   suite de 5 mots consécutifs** avec un des exemples (minuscules, ponctuation retirée,
   apostrophes comprises comme séparateur).
3. À la fin de chaque sous-série (`isole`) et à la fin du scénario `conversation`, imprimer :
   `RECOPIES : k/n` et `SILENCES (None) : k/n`.
4. Test dans `tests/test_sugar_persona.py` (pas de réseau) : `est_recopie("Me voilà. Ce chat
   manquait justement d'un peu de peps, Ahmed.", ["Me voilà. Ce chat manquait justement d'un
   peu de peps."])` est vrai ; une réponse sans suite commune de 5 mots est fausse ;
   `reponses_des_exemples(sugar_data.PERSONALITY_PROMPT)` renvoie autant de réponses que de
   lignes `→ «`.

**Mesure AVANT** (le code en prod, `1b17c98`) : **non**, elle existe déjà (tableau ci-dessus) ;
ne pas rebrûler le quota. Recompter seulement `apres_isole.txt` avec `est_recopie` pour vérifier
que la fonction retrouve ~41/72 (tolérance ±3). Si elle en trouve beaucoup moins, la fonction
est fausse : la corriger avant tout.

## LOT 2 — Exemples ACCROCHÉS au déclencheur, et une posture pour le prénom seul

`SugarBot/sugar_data.py`, les **trois premières** lignes du bloc EXEMPLES DE VOIX, **avant** :

```
- Provocation « t'es qu'un bot pourri » → « Pourri, et pourtant c'est toi qui reviens me parler. Drôle de régime, péteur. »
- Juste son prénom, sans rien d'autre → « Me voilà. Ce chat manquait justement d'un peu de peps. »
- Reproche gentil « t'es méchante » → « Promis, c'était de la taquinerie. Je range les griffes, tu gardes le sourire. »
```

**après** :

```
- Provocation « t'es qu'un bot pourri » → « Pourri ? Je sens la vanille, pas le moisi. Renifle mieux, péteur. »
- Juste son prénom, sans rien d'autre → elle répond présente et parle d'autre chose que le message (le jeu en cours, l'ambiance du chat) ; jamais deux fois la même entrée.
- Reproche gentil « tu m'as vexé » → « Vexé ? Alors je retire l'épine et je te laisse la rose. Trêve signée. »
```

Pourquoi ces formes : la provocation et le reproche répondent **au mot** du déclencheur
(« pourri », « vexé ») — face aux messages de la sonde (« nul », « c'est méchant »), ils ne
peuvent pas être collés tels quels. Le prénom seul n'a aucun mot auquel s'accrocher : on
donne la **posture**, pas une phrase à recopier.

⚠️ **Même nombre de lignes (5), longueur totale du bloc ≤ celle d'aujourd'hui** : la
frontière `PROHIBITED_CONTENT` (voir plus haut). Compter les caractères avant/après et les
écrire dans le commit. **Ne pas remettre « Question banale ».**
⚠️ Lignes 4-5 (compliment, doute) et le reste de la fiche : **ne bougent pas**.
⚠️ **Avant toute sonde**, un appel direct `google.genai` avec la fiche +
`ANTI_INJECTION_GUARD` (comme l'a fait Antigravity le 24/09, étape 102 de sa session) :
`prompt_feedback.block_reason` doit être `None`. Sinon, raccourcir la ligne 2 (la posture)
et recommencer — ne rien lancer d'autre tant que ce n'est pas `None`.

Mettre à jour le verrou `test_les_exemples_ne_jugent_plus_le_message` : `"Reproche gentil"`
reste ; ajouter que les motifs `"manquait justement"`, `"Drôle de régime"`, `"Je range les
griffes"` sont absents.

## LOT 3 — Mesure APRÈS, critères fixés MAINTENANT

**Budget de quota** : la clé Gemini de Sugar (`GEMINI_KEY_1`, 500 requêtes/jour sur
`gemini-3.5-flash-lite`) sert AUSSI la prod. Le 24/09, les essais l'ont épuisée une fois.
Donc : au plus **une** passe d'essai à `--n 6`, puis la passe finale (`isole --n 18` = 72
appels, `conversation --n 18` = 54). Pas de boucle de réglages au-delà : si ça échoue,
on rapporte. **Jamais pendant un live de `ma_streameuse`.**

| critère | seuil | 1b17c98 (prod) |
|---|---|---|
| **RECOPIES** (compte automatique, isolé) | **≤ 4/72** | ~41/72 |
| **RECOPIES** (conversation) | **≤ 3/54** | ~19/54 |
| **SILENCES (None)** | **0/126** | 0 |
| `sugar` seul : commente la forme / la brièveté / le vocabulaire | ≤ 4/18 | 0/18 (par recopie) — ~16/18 avant |
| `c'est mechant =(` : nouvelle pique sur la personne | ≤ 5/18 | 0/18 (par recopie) — ~10/18 avant |
| `dsl` : pardonne sans se moquer de l'excuse | ≥ 15/18 | 18/18 |
| `t'es qu'un bot nul` : riposte avec du mordant | ≥ 14/18 | 18/18 |
| une même réponse (hors prénom « Ahmed ») ≥ 3 fois dans une sous-série | **aucune** | 13 fois |

Les quatre lignes du bas se lisent réponse par réponse ; les trois du haut sont imprimées par
la sonde.

**Décision** :
- tout passe → LOT 4 ;
- recopies OK mais `sugar` repasse > 4/18 sur la forme → **ne pas livrer**, rapporter : la
  posture seule ne suffit pas ;
- recopies > seuil → **ne pas livrer**, rapporter les phrases recopiées : l'hypothèse
  « accroché au déclencheur » est fausse ;
- un seul SILENCE → **ne pas livrer** (frontière `PROHIBITED_CONTENT`).

**Le tableau complet, AVANT et APRÈS, va dans le message de commit — y compris les lignes
qui échouent.** Un commit qui ne reprend pas toutes les lignes de ce tableau ne respecte pas
le plan.

## LOT 4 — Vérifier, livrer

1. `python -m pyflakes tools/sonde_ton_twitch.py tests/test_sugar_persona.py SugarBot/sugar_data.py`
2. Suite complète, **un seul pytest à la fois** (port 8599) :
   `uv run --no-project --python 3.11 --with-requirements requirements.txt -- python -m pytest -q`
3. Commit (avec le tableau), push, **`gh run list --limit 1` → `success`**.

## LOT 5 — Prod **[Ahmed : hors live]**

`docker restart bot-sugar`. Au chat : deux « sugar » d'affilée (deux spectateurs) ne doivent
pas recevoir la même phrase.

---

# SUITE — relecture de `8bf1706` (Claude, 24/09 ~15:45)

Livré, CI verte, **en prod** (`bot-sugar` redémarré 13:30 UTC). Nettement mieux que `1b17c98`
(plus aucune récitation). Mais la validation complète a tourné sur **Mistral** (le repli), car le
quota Gemini de Sugar était épuisé ; or la prod répond d'abord avec **Gemini**. Sur Gemini
(sorties brutes `681bc267…/scratch/mesure_apres_isole.txt`) :

- `sugar` : recopies 0/18 ✅ ; forme du message **6/18** (seuil ≤ 4, dans le bruit ±3 ; ~16/18 avant) ;
- `sugar` : **~8/18 réponses finissent par une question** (« Tu cherches un bonbon ou… ? ») — la
  fiche l'interdit ; 1/18 avec `1b17c98`. Effet probable de la posture « parle d'autre chose » ;
- `c'est mechant` et `bot nul` : **2 réponses chacune** (quota) → non mesurés sur Gemini.

**[Antigravity, après 09:00 Paris le 25/09, hors live]** :
`--scenario isole --n 18 --seulement 2` puis `--seulement 3` (36 appels), et recompter la
sous-série `sugar` existante. Critères : ceux du tableau du LOT 3 + **questions finales ≤ 3/18**
sur `sugar`. Si la question finale dépasse : remplacer la ligne 2 (137 car. aujourd'hui) par
`- Juste son prénom, sans rien d'autre → elle répond présente et parle d'autre chose (jeu, ambiance), sans question.`
(plus courte : la frontière `PROHIBITED_CONTENT` est à ~145-152 car.), vérifier `block_reason`, remesurer `--seulement 0`. Rapporter les
chiffres, même s'ils passent.

## SUITE 2 — « là-bas » dans l'invitation `!discord` de Sugar (Claude, 24/09 soir)

**Constat** : la clause jeu de Sugar (`shared/twitch/dispatch.py`, `CLAUSES_JEU_PAR_BOT["sugar"]`)
dit « les invite à venir le raconter **là-bas** » — le mot est dans le prompt, il sort dans la
phrase, et il ne désigne plus rien : live du 23/09, « combien de fois vos armures ont-elles fini
par plier **là-bas** ? » (là-bas = la Bohême ?). Le Discord n'est jamais nommé. Seulement 2 phrases
réelles dans les journaux : **mesurer avant de toucher la prod.**

⚠️ La longueur (132 car. pour « 120 ») n'est PAS un bug : `_borner` coupe à 200 exprès
(21/09 : une coupe à 120 tranchait l'invitation). Ne pas y toucher.

**[Antigravity, 25/09 après 9 h, hors live, APRÈS la mesure de la SUITE — même quota]**
Sonde existante, option `--clause-jeu` ajoutée le 24/09 (n'altère pas la prod) :

```
python tools/sonde_phrase_de_lien.py --bot sugar --n 18 --jeu "Kingdom Come: Deliverance II" --fiche "Résumé : 15th century RPG set in Bohemia | Thèmes : Action, Historical"
python tools/sonde_phrase_de_lien.py --bot sugar --n 18 --jeu "Kingdom Come: Deliverance II" --fiche "Résumé : 15th century RPG set in Bohemia | Thèmes : Action, Historical" --clause-jeu "<VARIANTE>"
```

`<VARIANTE>` = la clause actuelle, recopiée **à l'identique**, avec un seul changement :
« les invite à venir le raconter là-bas » → « les invite à venir le raconter sur le serveur
Discord ». (Pas d'autre mot touché : on mesure ce changement-là.)

| critère (lecture phrase par phrase) | seuil pour livrer B |
|---|---|
| « là-bas » dans la phrase | B ≤ 2/18 |
| la destination est nommée (Discord / serveur) | B ≥ 14/18 |
| question aux lecteurs + invitation | B ≥ A − 3 |
| objet / contenu du Discord inventé | B ≤ A |
| longueur médiane | B ≤ A + 15 car. |
| repli sur le gabarit fixe | B ≤ A |

Tout passe → remplacer la clause dans `dispatch.py`, verrou dans
`tests/test_phrase_de_lien_jeu_en_cours.py` (« là-bas » absent de `CLAUSES_JEU_PAR_BOT["sugar"]`),
commit avec le tableau A/B complet. Sinon → rapporter les chiffres, ne rien livrer.
⚠️ Ne pas toucher au texte COMMUN (l.1100 « Ta phrase ne parle que de là-bas ») : le changer
touche les six bots, et le 21/09 chaque retouche commune a cassé M'aiq ou Malena.

## RESTE DES PLANS PRÉCÉDENTS

- **[Ahmed]** Annonces automatiques (`fb1bb4c`, en prod mais non réglées) : redémarrer le
  **dashboard** (hors Docker), régler « Auto (min) » et « Msgs min » (20 ≈ « l'annonce
  précédente n'est plus visible ») sur `!discord` de Sugar, Enregistrer, `docker restart bot-sugar`.
- **[Ahmed]** Alias `ma_streameuse` sur `!discord` (poste le lien Discord) : voulu ? Ajouter
  `disocrd` en alias si on veut que la faute de frappe marche.
- **Frontière `PROHIBITED_CONTENT`** : à comprendre un jour (longueur ? combinaison avec la
  garde anti-injection ?). Elle concerne potentiellement les SIX bots Twitch dès qu'une fiche
  s'allonge. Plan à écrire si Ahmed le veut.
- **LOT 7 du 22/09 [Ahmed]** — recréer `.venv` en 3.11.
- **Décret de Sheogorath** : 4 phrases pour « 1-2 », trois thèmes récités, titre > 32 car.

## INTERDITS DE CE PLAN

- Aucun `.env`, `.master_key`, `.env.encrypted`, ni base de `data/` touché.
- La sonde charge les clés de **Sugar seule** ; jamais pendant un live de `ma_streameuse`.
- Aucun import entre bots ; aucune factorisation. Ne pas toucher `shared/twitch/llm.py`.
- Ne toucher qu'aux trois premières lignes des EXEMPLES DE VOIX.
- **Un seul `pytest` à la fois.** Aucun lot « livré » tant que la CI n'est pas `success`.
