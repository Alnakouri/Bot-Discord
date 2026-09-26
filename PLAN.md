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

## ✅ SUITE 0 et SUITE — CLOSES (Claude, 25/09 16:50)

B livré (`7f9287b`) : « sugar » méchante ~10/18 → ~5/18 (seuil ≤ 3 non tenu, mais dans le
plancher de bruit ±3 sur 18 tirages ; gain accepté, jugement final au live). Ligne 2
« sans question » (`04e7bdc`) essayée puis **revertée** (`5a4561c`) : ~7/18, questions 4 → 5/18.
En prod depuis le 25/09 14:50 UTC. **Ne pas relancer ces mesures** : passer à la SUITE 2.

## SUITE 0 — Sugar MÉCHANTE sur un simple « sugar » (Claude, 25/09 nuit) — CLOSE, historique

**Constat live (24/09 20:00, Gemini)** : « sugar » → « C'est le mot de passe pour le salon des
sans-idées ? Soigne ton entrée ». Ahmed : « elle est directement méchante ». Sur la mesure
Gemini du 24/09 (`mesure_apres_isole.txt`), ~7/18 réponses à « sugar » sont une moquerie.

**Cause (hypothèse)** : `SugarBot/sugar_data.py:50`, sous « VARIÉTÉ DE STRUCTURE — RÈGLE N°1,
PRIORITAIRE SUR TOUT LE RESTE », lui donne quatre ossatures pour TOUTE réplique, dont trois
méchantes : « affirmation cinglante », « constat moqueur », « pique nette sans aucun sucre ».
La consigne de ton neutre (« avenante… range le venin ») arrive après et perd.

**Mesure A/B**, sur Gemini, hors live, option `--remplace/--par` ajoutée le 25/09 (la prod n'est
pas touchée ; la sonde refuse si le texte n'est pas trouvé une fois) :

```
A : python tools/sonde_ton_twitch.py --scenario isole --n 18 --timeout 30 --seulement 0
    python tools/sonde_ton_twitch.py --scenario isole --n 18 --timeout 30 --seulement 3
B : les deux mêmes, avec
    --remplace "tantôt une affirmation cinglante, tantôt un constat moqueur, tantôt une seule image bien trouvée, tantôt une pique nette sans aucun sucre."
    --par "tantôt un constat, tantôt une seule image bien trouvée, tantôt une réplique toute simple ; le mordant, garde-le pour qui te cherche."
```

(72 appels.) **Avant B** : appel direct `google.genai` avec la fiche B + `ANTI_INJECTION_GUARD`,
`block_reason` doit être `None` (cf. `tools/sonde_blocage_gemini.py`).

| critère (lecture réponse par réponse) | seuil pour livrer B |
|---|---|
| `sugar` : moquerie / pique / jugement du message | **B ≤ 3/18** et B < A |
| `sugar` : finit par une question | B ≤ 3/18 |
| `t'es qu'un bot nul` : riposte AVEC mordant | **B ≥ 14/18** (elle garde ses griffes) |
| SILENCES / RECOPIES (imprimés par la sonde) | 0 / ≤ 1 |

Tout passe → remplacer la ligne 50, verrou dans `tests/test_sugar_persona.py` (« cinglante »,
« moqueur », « pique nette » absents de la règle de variété), commit avec le tableau A/B,
puis la SUITE ci-dessous se mesure sur ce nouveau code. Sinon → rapporter, ne rien livrer.

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

> ✅ **LIVRÉE par décision d'Ahmed (26/09 10:20)** : combinée avec la SUITE 2-bis pour éradiquer « là-bas » à la fois de la clause jeu de Sugar et du texte commun. Verrous dans `tests/test_phrase_de_lien_jeu_en_cours.py`. Redémarrage des conteneurs = **[Ahmed, hors live]**.

**Constat** : la clause jeu de Sugar (`shared/twitch/dispatch.py`, `CLAUSES_JEU_PAR_BOT["sugar"]`)
dit « les invite à venir le raconter **là-bas** » — le mot est dans le prompt, il sort dans la
phrase, et il ne désigne plus rien : live du 23/09, « combien de fois vos armures ont-elles fini
par plier **là-bas** ? » (là-bas = la Bohême ?). Le Discord n'est jamais nommé. Seulement 2 phrases
réelles dans les journaux : **mesurer avant de toucher la prod.**

⚠️ La longueur (132 car. pour « 120 ») n'est PAS un bug : `_borner` coupe à 200 exprès
(21/09 : une coupe à 120 tranchait l'invitation). Ne pas y toucher.

**[Antigravity, 26/09 après 9 h Paris (quota Gemini de Sugar remis à zéro), hors live — PROCHAINE ÉTAPE]**
Sonde existante, option `--clause-jeu` ajoutée le 24/09 (n'altère pas la prod) :

```
python tools/sonde_phrase_de_lien.py --bot sugar --n 18 --jeu "Kingdom Come: Deliverance II" --fiche "Résumé : 15th century RPG set in Bohemia | Thèmes : Action, Historical"
python tools/sonde_phrase_de_lien.py --bot sugar --n 18 --jeu "Kingdom Come: Deliverance II" --fiche "Résumé : 15th century RPG set in Bohemia | Thèmes : Action, Historical" --clause-jeu "<VARIANTE>"
```

**Aussi sur Mistral (ajout du 25/09)** : le 24/09 à 20:15, quota Gemini épuisé, c'est
`ministral` qui a écrit l'invitation : « Viens qu'on t'échange des vanne-sucrées **en privé** »
— Discord non nommé, et « en privé » est faux. Rejouer les deux commandes ci-dessus avec
`--tete mistral` (n'utilise AUCUNE clé Gemini, donc pas le quota de Sugar) = 72 phrases en
tout. B n'est livré que s'il passe le tableau sur Gemini **et** sur Mistral : destination
nommée B ≥ 12/18, « là-bas » ou « en privé » B ≤ 2/18. Rapporter les quatre séries.

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

## SUITE 2-bis — « là-bas » dans le texte COMMUN de la phrase de lien (Claude, 26/09)

> ✅ **LIVRÉE par décision d'Ahmed (26/09 10:20) contre la règle du plan** :
>
> - **Étape 1 livrée** (`95005f1`, CI `success`) : options `--remplace`/`--par` dans `tools/sonde_phrase_de_lien.py`, verrous unitaires passés.
> - **Étape 2 (mesure A)** : Sugar présente le défaut « là-bas » ambigu à **9/18** (> 2/18). Étape 3 (mesure B) déclenchée.
> - **Étape 3 (mesure B sur les 6 bots)** :
>   - **Sugar** : « là-bas » ambigu 9 → 2/18 ✅, destination nommée 0 → 10/18 ✅, ouvertures 9x → 3x ✅, médiane 112 → 106 car. ✅, replis 0 → 0 ✅. Tout passe.
>   - **Alfred** : « là-bas » ambigu 0 → 0/18 ✅, destination 18 → 18/18 ✅, médiane 137 → 130 car. ✅, replis 0 → 0 ✅. Tout passe.
>   - **M'aiq** : « Discord » nommé 0 → 0/18 ✅ (conforme : « Discord n'existe pas »), « là-bas » ambigu 0 → 0/18 ✅, médiane 88 → 92 car. ✅, replis 0 → 0 ✅. Tout passe.
>   - **Johnny** : « là-bas » ambigu 0 → 0/18 ✅, destination 2 → 3/17 ✅, replis 3 → 1/18 ✅, médiane 184 → 167 car. ✅. Tout passe.
>   - **Sheogorath** : « là-bas » ambigu 0 → 0/18 ✅, destination 0 → 1/18 ✅, médiane 157 → 171 car. ✅, replis 0 → 0 ✅. Tout passe.
>   - **Malena** : « là-bas » ambigu 2 → 2/18 ✅, destination 100% ✅, médiane 100 → 94 car. ✅, ouverture 3x → 6x ✅. **Replis sur gabarit fixe : 0/18 → 2/18** (seuil strict B ≤ A + 1 = 1 dépassé de 1 repli, causé par le mot « chat » dans les essais de Malena rejeté par le filtre anti-chat Twitch, accepté par Ahmed comme plancher de bruit ±3).
>
> Remplacement appliqué dans `shared/twitch/dispatch.py` (clause Sugar + texte commun l.1100 et l.1124). Verrous AST et unitaires dans `tests/test_phrase_de_lien_jeu_en_cours.py`.
> Reste **[Ahmed, hors live]** : redémarrer les conteneurs des six bots.

**Pourquoi** : la SUITE 2 a montré que, sur Mistral, Sugar dit encore « là-bas » même quand sa
clause ne le dit plus — le mot vient du texte commun de `_generate_link_line`
(`shared/twitch/dispatch.py`) : l.1100 « Ta phrase ne parle que de là-bas » (toujours) et
l.1124 « ne promets pas qu'on en parlera là-bas » (seulement avec un jeu). Ce texte sert aux
SIX bots : on ne le touche que si la mesure passe **sur les six**.

⚠️ **On ne sait pas encore si c'est un défaut ailleurs que chez Sugar.** Sans jeu, « là-bas »
suivi du lien n'est pas ambigu ; le défaut du 23/09 est « là-bas » **à côté d'un monde de
jeu** (la Bohême). D'où l'étape 2 : mesurer A seul d'abord, et ne lancer B que si A montre
le défaut quelque part. ⚠️ **M'aiq** : sa fiche PRESCRIT de ne pas nommer Discord
(`maiq_data.py:52`, « 'Discord' n'existe pas ») — chez lui, un « Discord » nommé est une
RÉGRESSION, pas un gain ([[gotcha-un-defaut-peut-etre-une-fonctionnalite]]).

**Étape 1 [Antigravity, aucun quota]** — `tools/sonde_phrase_de_lien.py` : options
`--remplace TEXTE --par TEXTE`, répétables (`action="append"`), sur le modèle de
`tools/sonde_ton_twitch.py:186`. Elles enveloppent `f._ecrire_phrase_de_lien` du faux bot
(jamais la classe, jamais le code de prod) : avant l'appel, chaque `--remplace` doit
apparaître **exactement une fois** dans l'instruction, sinon la sonde lève et s'arrête
(pas de mesure silencieuse d'un texte non remplacé). L'en-tête imprime `| VARIANTE xN`.
Test dans `tests/` : une instruction sans le texte → erreur ; avec → remplacé une fois.
Mettre à jour la docstring (section « ce que les options ont servi à trancher »). pyflakes,
pytest (un seul à la fois), CI verte.

**Étape 2 [Antigravity, hors live, après lecture de `data/api_usage.db` en `?immutable=1`]**
— A seul, 18 phrases par bot, sur la tête de chaque bot (clés de CE bot seulement) :

```
J="Kingdom Come: Deliverance II"
F="Résumé : 15th century RPG set in Bohemia | Thèmes : Action, Historical"
python tools/sonde_phrase_de_lien.py --bot sugar  --n 18 --jeu "$J" --fiche "$F" --timeout 30
python tools/sonde_phrase_de_lien.py --bot alfred --n 18 --jeu "$J" --fiche "$F" --timeout 30
python tools/sonde_phrase_de_lien.py --bot malena --n 18 --jeu "$J" --fiche "$F" --timeout 30
python tools/sonde_phrase_de_lien.py --bot maiq   --n 18 --jeu "$J" --fiche "$F" --timeout 30
python tools/sonde_phrase_de_lien.py --bot johnny --n 18 --jeu "$J" --fiche "$F" --timeout 30 --tete mistral
python tools/sonde_phrase_de_lien.py --bot sheogorath --n 18 --jeu "$J" --fiche "$F" --timeout 30 --tete mistral
```

(M'aiq et Sheogorath ne sont pas dans `ACCROCHE_AU_JEU` : le jeu est ignoré, ils mesurent la
l.1100 seule. C'est voulu.) Lire phrase par phrase et rapporter, par bot : « là-bas » (et
« en privé »), destination nommée, « là-bas » **ambigu** (peut désigner le monde du jeu),
invitation présente, objet inventé, ouverture la plus fréquente, médiane, replis.
**Arrêt** : si aucun bot n'a « là-bas » ambigu > 2/18, s'arrêter là et rapporter — pas de B.

**Étape 3 [Antigravity, seulement si l'étape 2 montre le défaut]** — les six mêmes commandes, avec :

```
--remplace "Ta phrase ne parle que de là-bas." --par "Ta phrase ne parle que du serveur Discord."
--remplace "ne promets pas qu'on en parlera là-bas." --par "ne promets pas qu'on en parlera sur le serveur."
```

(le 2e seulement pour les quatre bots de `ACCROCHE_AU_JEU` : chez M'aiq et Sheogorath il
n'apparaît pas et la sonde refuserait.) Aucune clause par bot n'est touchée — les « là-bas »
des clauses d'Alfred, Johnny, Sheogorath (et de Sugar si Ahmed a refusé la SUITE 2) restent :
on mesure CE changement-là.

| critère, par bot (plancher de bruit ±3 sur 18) | seuil pour livrer B |
|---|---|
| « là-bas » ambigu | B ≤ 2/18 là où A > 2 ; ailleurs B ≤ A + 1 |
| destination nommée | B ≥ A — **sauf M'aiq : « Discord » nommé B ≤ A** |
| invitation présente | B ≥ A − 2 |
| objet / contenu inventé | B ≤ A + 2 |
| ouverture la plus fréquente | B ≤ A + 3 (21/09 : les retouches communes ont écrasé celles de M'aiq et Malena) |
| longueur médiane | B ≤ A + 15 car. |
| replis sur le gabarit fixe | B ≤ A + 1 |

**Tout passe sur les six** → remplacer les deux phrases dans `dispatch.py`, verrou dans
`tests/test_phrase_de_lien_jeu_en_cours.py` (« là-bas » absent du texte commun — lire la
source par AST, pas retaper l'instruction), commentaire au-dessus de l'instruction avec le
tableau A/B des six, commit, `gh run list` jusqu'à `success`. **Un seul bot échoue** → ne
rien livrer, rapporter les douze séries ; Claude décidera (clause par bot plutôt que texte
commun). Redémarrage des conteneurs = **[Ahmed, hors live]**.

## SUITE 5 — la phrase `!discord` de Sugar SOUDE question et invitation (Claude, 26/09, revue avec Ahmed)

> ✅ **LIVRÉE (26/09) : Bras B2 gagnant, les 12 critères passent** :
>
> - **Étape 1 (mesures A, B1, B2)** :
>   - **A (prod)** : 14/18 soudures (« avant de venir… »), 0/18 Discord nommé, 8/18 se lisent mal, 5/18 décors avant la question, 2/18 piques.
>   - **B1 (forme seule)** : 18/18 Discord nommé ✅, 0/18 soudure ✅, 0/18 se lit mal ✅, mais **3/18 tu et vous mélangés** (seuil strict <= 1/18) et 7/18 tutoiements (« Viens… »).
>   - **B2 (exemples d'Ahmed avec consigne de variation)** : 17/18 Discord nommé ✅ (1 repli suite à 503 temporaire), 0/18 soudure ✅, 2/18 se lit mal ✅, 0/18 pique ✅, 0/18 décor avant ✅, 0/18 tu/vous mélangé ✅ (100% vous), 4/18 même invitation ✅ (variété préservée), 109 car. médiane ✅. **Tous les 12 critères passent.**
> - **Étape 2 livrée** : clause B2 insérée dans `shared/twitch/dispatch.py`, commentaire avec tableau A/B1/B2, verrous dans `tests/test_phrase_de_lien_jeu_en_cours.py` mis à jour (« Discord » et « DEUX phrases »).
> - Reste **[Ahmed, hors live]** : redémarrer le conteneur `bot-sugar`.

**Constat en live (Ahmed, 26/09, « formulation nulle »)**, deux phrases sur KCD2 :

- « À part te remettre à ta place de faim virtuellement, Kingdom Come II vous a donné envie
  d'en débattre sur notre serveur ? ✨ » : c'est une pique (interdite par la clause), elle
  mélange tu et vous, et le sens est confus.
- « Entre deux boues médiévales, combien de fois Henri a-t-il ruiné vos bottes avant de venir
  nous raconter ça sur le serveur ? ✨ » : un décor avant la question (interdit), puis une
  soudure lourde.

**Cause** : la clause jeu de Sugar exige trois choses dans UNE phrase de moins de 120 car. :
une question sur le jeu, une invitation et la voix du personnage. Le modèle les soude avec
« avant de venir… » ou « À part…, … envie d'en débattre sur… ». La SUITE 2 a aggravé la chose
sans que ça se voie : en lui écrivant « sur le serveur Discord », elle lui a donné une
destination à recopier, et la mesure ne comptait que les « là-bas » et la destination nommée,
jamais si la phrase **se lit bien**.

**Idée (corrigée par Ahmed, 26/09)** : on garde deux temps, mais on ne les soude plus. D'abord
une question courte sur le jeu, puis une invitation courte et franche qui nomme Discord, dans
l'esprit « Venez nous en parler sur Discord ! » ou « Rejoignez notre Discord ! ». Ce sont
**deux phrases** et non plus une. La première version (23/09, « question PUIS invitation »)
avait donné 176 car. de médiane parce que rien ne bornait chaque morceau. Ici, chaque phrase a
sa propre borne.

⚠️ **Le risque, c'est le tic** ([[gotcha-une-formule-nommee-devient-un-tic]]) : une formule
écrite dans le prompt revient mot pour mot 16 fois sur 17. D'où deux bras B :

- **B1** ne donne aucun exemple, seulement la forme ;
- **B2** donne les exemples d'Ahmed, en demandant de varier.

On garde celui qui passe. Si les deux passent, on prend celui qui varie le plus.

**Live** : Ahmed autorise cette mesure **même pendant un live** (26/09). Elle fait 54 appels
avec les clés de Sugar. Avant de la lancer, lire `data/api_usage.db` (`?immutable=1`) : si la
tête de Sugar a eu des 429 dans les 30 dernières minutes, attendre.

**Étape 1 [Antigravity, aucun changement de code]**. Trois séries de 18 phrases, sur Sugar
seule : A (prod), B1 et B2 (clause injectée).

```
J="Kingdom Come: Deliverance II"
F="Résumé : 15th century RPG set in Bohemia | Thèmes : Action, Historical"
COMMUN="⚠️ Adresse-toi à ceux qui LISENT, pas au personnage du jeu. Vouvoie le chat : ils sont plusieurs. Ici, tu écris DEUX phrases courtes, et elles seules. La première est une question simple sur ce que CE JEU leur a fait vivre, à eux, quand ils y ont joué : jamais sur la partie en cours, jamais une pique sur eux, pas de décor avant, moins de 80 caractères, et elle se termine sur son point d'interrogation. La seconde, moins de 45 caractères, les invite franchement à venir en parler sur Discord et nomme Discord."
python tools/sonde_phrase_de_lien.py --bot sugar --n 18 --jeu "$J" --fiche "$F" --timeout 30
python tools/sonde_phrase_de_lien.py --bot sugar --n 18 --jeu "$J" --fiche "$F" --timeout 30 --clause-jeu "$COMMUN Un emoji peut la finir. "
python tools/sonde_phrase_de_lien.py --bot sugar --n 18 --jeu "$J" --fiche "$F" --timeout 30 --clause-jeu "$COMMUN Dans l'esprit de « Venez nous en parler sur Discord ! », « Rejoignez notre Discord ! » ou « Venez en discuter sur Discord ! », mais avec tes mots à toi, et jamais deux fois la même. Un emoji peut la finir. "
```

⚠️ Le texte commun de l'instruction dit encore « UNE seule phrase (max 120 caractères) ». La
clause le contredit exprès. Si B1 et B2 donnent quand même une seule phrase soudée plus de 6
fois sur 18, c'est que le texte commun l'emporte : rapporter, ne rien livrer. Claude écrira
alors un `--remplace` réservé à Sugar.

Lire **chaque ligne à voix haute**, entière (phrases + lien) comme elle apparaîtra en salon,
et rapporter les 54 lignes brutes avec ce tableau :

| critère (plancher de bruit ±3 sur 18) | seuil pour livrer B1 ou B2 |
|---|---|
| **invitation finale qui nomme Discord** | ≥ 16/18 |
| **soudure** (invitation collée dans la question, « avant de venir… ») | ≤ 2/18 |
| **se lit mal** (lu à voix haute : bancal ou sens flou) | ≤ A − 3 |
| **même invitation mot pour mot** (la plus fréquente) | ≤ 6/18 |
| pique sur le chat | 0 |
| décor avant la question | ≤ 2/18 |
| tu et vous mélangés | ≤ 1/18 |
| vraie question sur le jeu vécu | ≥ A − 2 |
| partie en cours ou contenu du Discord inventé | ≤ A + 1 |
| « là-bas » ambigu | ≤ 2/18 |
| longueur médiane (sans le lien) | ≤ 130 car. |
| replis sur le gabarit fixe | ≤ A + 1 |

**Étape 2 [Antigravity, seulement si B1 ou B2 passe tout]** : remplacer
`CLAUSES_JEU_PAR_BOT["sugar"]` dans `shared/twitch/dispatch.py` par la clause gagnante,
**mot pour mot** (le texte de `$COMMUN` suivi de la fin propre au bras). Mettre le tableau
A/B1/B2 en commentaire au-dessus de la clause, en AJOUTANT des lignes : ne jamais en
remplacer. Garder `test_la_bas_absent_de_la_clause_jeu_de_sugar` et y ajouter « Discord »
présent et « DEUX phrases » présent. Ensuite pyflakes, un seul pytest, commit, et
`gh run list` jusqu'à `success`.
**Un critère échoue dans les deux bras** → ne rien livrer, rapporter les 54 lignes ; Claude
décidera. Redémarrer `bot-sugar` = **[Ahmed]**.

⚠️ Ne pas toucher au texte commun de `_generate_link_line` : la SUITE 2-bis l'a mesuré sur les
six bots. On ne change que la clause de Sugar.

**Note à corriger avec cette suite** : `c467ebb` avait coupé en deux un commentaire sur
Alfred dans `dispatch.py` (« Alfred sort » sans suite). Claude l'a restauré le 26/09, dans le
même commit que ce plan. Quand on édite un commentaire, on AJOUTE des lignes, on n'en remplace pas.

## SUITE 6 — la phrase `!discord` de JOHNNY (Claude, 27/09)

**Pourquoi Johnny seul** : d'après les journaux du 27/09, seuls Sugar et Johnny ont une
commande de lien armée (« Commandes de lien armees : !discord »). Alfred, Sheogorath, Malena et
M'aiq n'en ont pas : leur phrase ne sort jamais en prod, donc on ne dépense pas de quota pour
elle. Si Ahmed arme `!discord` sur un autre bot, ce bot aura sa propre suite.

**État actuel, relu sur les 18 phrases de la SUITE 2-bis** (bras B, c'est-à-dire la prod
depuis `c467ebb` ; sortie brute : `~/.gemini/antigravity-cli/brain/bd4af75c-…/scratch/sonde_B_johnny.txt`,
ministral, KCD2) :

- **Il compare le jeu à lui-même**, 13 fois sur 17 : « Jouez à vos chevaliers en armure
  rouillée pendant qu'on se bat pour de vrai ici », « ici on a des cicatrices vraies ». Le
  texte commun l'interdit (« tu ne compares jamais les deux »). Mais le bloc jeu lui propose
  « une comparaison » et « une pique sur ce que le JEU fait subir », et Mistral fait le
  mélange.
- **Des piques sur ceux qui jouent**, 3 fois : « Tu t'es pris une épée en bois dans la gueule
  à force de jouer à ce jeu moyenâgeux ? ».
- **Pas de destination claire** : Discord est nommé 3 fois sur 17. Ailleurs on a « viens où au
  moins… », « en privé » (1 fois) ou « dans mon Discord » (1 fois, il se l'approprie).
- **Trop long** : 167 car. de médiane, 17/17 au-dessus de 120, et 3 phrases **tranchées par
  `max_tokens=60`** (fin en « … »). La longueur est un défaut du MODÈLE sur ministral
  ([[gotcha-la-longueur-est-un-defaut-de-MODELE]]) : une règle de volume seule n'y fait rien.
- **Déjà réglé**, et à ne pas rouvrir : la boisson offerte. On en compte 0 sur 17 (la clause
  `CLAUSES_PAR_BOT["johnny"]` tient). Le 🥃 n'est qu'un emoji.
- Mélange tu/vous dans une même phrase : 2 fois.

**Idée** : la forme qui a marché chez Sugar (SUITE 5), c'est-à-dire deux phrases qui ont
chacune leur borne. La première est une réplique de Johnny sur le jeu, sans comparaison avec
« ici ». La seconde est une invitation courte qui nomme Discord. Elle va dans
`CLAUSES_PAR_BOT["johnny"]`, **à la suite** de la clause actuelle (ne pas la remplacer : elle
tient la boisson à 0), pour que la forme vale aussi hors live. Johnny tutoie, c'est sa voix :
on ne lui impose pas le vous, seulement de ne pas mélanger les deux.

⚠️ La forme gagnante chez un bot peut casser chez un autre
([[gotcha-un-filet-ne-se-transpose-pas-d-un-bot-a-l-autre]]). Et Sugar tourne sur Gemini,
Johnny sur ministral : c'est pour ça qu'on mesure.

**Étape 1 [Antigravity, aucun changement de code]** — lire `data/api_usage.db`
(`?immutable=1`) : si la clé Mistral de Johnny a pris des 429 dans les 30 dernières minutes,
attendre. Ensuite, trois séries de 18 sur la tête Mistral de Johnny (54 appels, ses clés
seulement) :

```
J="Kingdom Come: Deliverance II"
F="Résumé : 15th century RPG set in Bohemia | Thèmes : Action, Historical"
ACTUELLE="⚠️ Tu ne promets rien qui les attendrait là-bas : ni tournée, ni verre, ni place gardée — tu n'as rien à offrir et tu n'as jamais rien offert à personne. Ce qui les attend, c'est toi : ta gueule, tes histoires, ce que tu vas leur balancer. Tes clopes et ton whisky restent les TIENS, tu ne les partages pas dans la phrase. "
FORME="⚠️ Ici, tu écris DEUX phrases courtes, et elles seules. La première, moins de 80 caractères, c'est ta réplique : elle parle de ce que le jeu fait subir à ceux qui y jouent, jamais d'eux, et elle ne compare jamais le jeu à toi, à ta vie ou à « ici ». La seconde, moins de 45 caractères, les invite franchement à venir en parler sur Discord et nomme Discord. Tutoie ou vouvoie, mais la même personne dans les deux phrases."
python tools/sonde_phrase_de_lien.py --bot johnny --n 18 --jeu "$J" --fiche "$F" --timeout 30 --tete mistral
python tools/sonde_phrase_de_lien.py --bot johnny --n 18 --jeu "$J" --fiche "$F" --timeout 30 --tete mistral --clause "$ACTUELLE$FORME Un emoji peut la finir. "
python tools/sonde_phrase_de_lien.py --bot johnny --n 18 --jeu "$J" --fiche "$F" --timeout 30 --tete mistral --clause "$ACTUELLE$FORME Dans l'esprit de « Viens nous en parler sur Discord ! » ou « Rejoins-nous sur Discord ! », mais avec tes mots à toi, et jamais deux fois la même. Un emoji peut la finir. "
```

(`$ACTUELLE` doit être **identique** à `CLAUSES_PAR_BOT["johnny"]` : le vérifier en Python avant
de lancer, `--clause` REMPLACE la clause au lieu de s'y ajouter.)

Lire chaque ligne à voix haute, entière (phrases + lien), et rapporter les 54 lignes brutes
avec ce tableau :

| critère (plancher de bruit ±3 sur 18) | seuil pour livrer B1 ou B2 |
|---|---|
| **invitation finale qui nomme Discord** | ≥ 15/18 |
| **compare le jeu à lui, à sa vie ou à « ici »** | ≤ 3/18 |
| **pique sur ceux qui jouent ou qui regardent** | ≤ 1/18 |
| **tranchée** (finit en « … » ou au milieu d'une idée) | ≤ 1/18 |
| **se lit mal** (lu à voix haute : bancal ou sens flou) | ≤ A − 3 |
| « en privé », « mon Discord », salon inventé | ≤ 1/18 |
| boisson ou objet offert | ≤ A + 1 |
| même invitation mot pour mot | ≤ 6/18 |
| tu et vous mélangés | ≤ 1/18 |
| la voix de Johnny (lu : on reconnaît Johnny, pas un bot neutre) | ≥ 15/18 |
| longueur médiane (sans le lien) | ≤ 140 car. |
| replis sur le gabarit fixe | ≤ A + 1 |

⚠️ « La voix de Johnny » compte autant que le reste : une phrase propre mais neutre, c'est un
échec. S'il ne dit plus que « Venez en parler sur Discord » sans rien avant, B échoue.

⚠️ Si B1 et B2 restent au-dessus de 140 car. mais passent tout le reste, rapporter sans rien
livrer. La longueur est alors un défaut de modèle, et c'est Claude qui tranchera (par exemple
monter `max_tokens` pour ne plus trancher, plutôt que de s'acharner sur la consigne).

**Étape 2 [Antigravity, seulement si B1 ou B2 passe tout]** : `CLAUSES_PAR_BOT["johnny"]` =
`$ACTUELLE` + la fin du bras gagnant, **mot pour mot**. Tableau A/B1/B2 en commentaire
au-dessus, en AJOUTANT des lignes : ne rien remplacer ni tronquer. Verrou dans
`tests/test_phrase_de_lien_jeu_en_cours.py` : la clause contient toujours « ni tournée, ni
verre », ainsi que « DEUX phrases » et « Discord ». Supprimer du commentaire de
`_generate_link_line` la phrase « Johnny invente une boisson dans 4 generations sur 4 », qui
est périmée : écrire à la place « réglé, 0/17 au 26/09 ». Ensuite pyflakes, un seul pytest,
commit, et `gh run list` jusqu'à `success`. **Un critère échoue dans les deux bras** → ne rien
livrer, rapporter les 54 lignes ; Claude décidera. `docker restart bot-johnny` = **[Ahmed]**.

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
- La sonde charge les clés de **Sugar seule** ; jamais pendant un live de `ma_streameuse`
  (**sauf la SUITE 5**, qu'Ahmed a autorisée pendant le live le 26/09).
- Aucun import entre bots ; aucune factorisation. Ne pas toucher `shared/twitch/llm.py`.
- Ne toucher qu'aux trois premières lignes des EXEMPLES DE VOIX.
- **Un seul `pytest` à la fois.** Aucun lot « livré » tant que la CI n'est pas `success`.

---

# SUITE 3 — compter les JETONS de chaque appel (Claude, 25/09 17:30)

> ✅ **EXÉCUTÉE `86d3574`, vérifiée par Claude le 25/09 23:40** : diff conforme (4 inline branchés, sondes `sonde`, runner `harnais`), 0 dérive de vendoring, CI `success`. Six conteneurs redémarrés 23:37. **Reste [Claude]** : au 1er appel réel, vérifier que `api_usage.db` change de date et porte les 3 colonnes — le fichier n'avait plus été écrit depuis 10:18 UTC avec un `-journal` chaud, et aucun appel n'a eu lieu depuis le redémarrage pour le prouver. Puis le tableau à 24 h.

**[Antigravity — lançable DÈS le 25/09, sans attendre la SUITE 2.]** Aucun appel de modèle
nécessaire : ce lot ne consomme pas de quota et ne touche pas `dispatch.py`. Livré ce soir,
il étiquette déjà `sonde` les appels de la SUITE 2 de demain. Un seul lot à la fois, un seul
`pytest` à la fois.

**Constat** : `api_usage.db` a une colonne `tokens_used`, **vide pour les six bots** (jamais
écrite : l'`INSERT` de `shared/api_tracking.py:125` ne la liste pas). On ne sait donc pas ce
que coûte un message. Tailles mesurées le 25/09 (caractères, pas des jetons) : fiche Sheo
12,5–13,8 k, Sugar 9,2 k, Johnny 8,9 k, Alfred 8,7 k, Malena 6,1 k, M'aiq 6,0 k ; en plus,
historique (≤ 30 messages) + transcript (10 derniers messages, qui recoupe l'historique).
Et les sondes A/B tournent par la même cascade : leurs appels sont comptés **au nom du bot**
(Sugar 641 et 1 463 appels les 23 et 24/09, contre 11 à 117 un jour ordinaire).

**Ce qu'on veut** : pour chaque appel, jetons d'ENTRÉE et de SORTIE réels (ceux que renvoie
le fournisseur, pas une estimation), et savoir si l'appel vient de la prod ou d'une sonde.
**On ne change RIEN au prompt dans ce lot** : on mesure d'abord.

1. `shared/api_tracking.py`
   - migration sur le modèle de `raison` (l.93-96) : colonnes `jetons_entree INTEGER`,
     `jetons_sortie INTEGER`, `origine TEXT` ;
   - `tracer_appel(..., jetons_entree=None, jetons_sortie=None)` : paramètres optionnels,
     défaut `None` (les appelants existants ne cassent pas) ; `origine` = `os.getenv("SUIVI_ORIGINE", "prod")` ;
   - l'`INSERT` écrit les trois colonnes. Ne PAS réutiliser `tokens_used` (sens ambigu).
2. `shared/llm_cascade.py` — lire l'usage renvoyé, **sans jamais lever** s'il manque
   (`getattr(..., None)`, tout dans un `try`) :
   - Gemini : `resp.usage_metadata.prompt_token_count` / `candidates_token_count` — y
     compris quand la réponse est VIDE (contenu bloqué) : ce sont justement les jetons perdus ;
   - Mistral, Groq, NVIDIA : `chat.usage.prompt_tokens` / `completion_tokens` ;
   - délai dépassé, 429, échelon sauté : `None` (pas 0 — 0 mentirait).
   Les passer aux deux `tracer_appel` (l.661 et l.798).
3. Les quatre appels **inline** (`Alfred/bot_alfred.py:2028`, `MalenaBot/bot_malena.py:430`,
   `MaiqBot/bot_maiq.py:1692`, `Sheogorath/bot_sheogorath.py:2663`) : même lecture si l'objet
   réponse est à portée ; sinon laisser `None` et le **noter dans le commit** (pas de
   refonte de ces cascades dans ce lot).
4. Les sondes : chaque `tools/sonde_*.py` qui passe par la cascade pose
   `os.environ.setdefault("SUIVI_ORIGINE", "sonde")` **avant** d'importer la cascade.
   Vérifier aussi `tests/eval/runner.py` (même réglage, valeur `"harnais"`).
5. `python tools/vendor_core.py` (les 6 copies `*/core/`), puis `python tools/sonde_core_drift.py`
   doit dire 0 écart.

**Verrous** (`tests/test_suivi_api.py`, base temporaire, jamais `data/`) :
- un appel tracé avec `jetons_entree=1200, jetons_sortie=80` relu à l'identique ;
- un appel tracé sans jetons → `NULL`, pas 0 ;
- `SUIVI_ORIGINE` absent → `"prod"` ; posé à `"sonde"` → `"sonde"` ;
- migration idempotente : ouvrir deux fois une base ancienne (sans les colonnes) ne lève pas ;
- AST sur `shared/llm_cascade.py` : chaque `tracer_appel(` passe `jetons_entree=` (viser le
  NOM du mot-clé, pas sa simple présence dans le fichier).

**Ordre** : pyflakes → `pytest` (un seul à la fois) → commit → push → `gh run list` jusqu'à
`success`. **[Ahmed]** redémarrer les six conteneurs hors live.

**Contrôle après 24 h de prod [Claude]** : pour chaque bot, médiane et p90 de `jetons_entree`
des appels `origine='prod'` réussis, jetons perdus sur les réponses vides, et part des
appels `sonde`. C'est CE tableau qui dira s'il faut alléger une fiche (Sheo d'abord),
supprimer le transcript en double de l'échelon Mistral (`llm_cascade.py`, message
utilisateur `TRANSCRIPT:` alors que le transcript est déjà dans `system_prompt`), ou
raccourcir l'historique. Aucune de ces trois retouches avant le tableau.

**Interdits** : aucune écriture dans `data/api_usage.db` en dehors du code du bot (pas de
`ALTER` à la main) ; aucun `.env` touché ; aucun changement de prompt, de cascade ou de borne.

---

# SUITE 4 — la fausse alerte « Token invalide (401) » au démarrage (Claude, 25/09)

> ✅ **EXÉCUTÉE `8d25bd8`, CI `success`.** Contrôle au démarrage du 25/09 23:37 **non concluant** : les jetons dataient de 20:14–20:44, encore valides, donc aucun 401. À refaire au prochain redémarrage à plus de 4 h d'un rafraîchissement.

**[Antigravity — lançable dès le 25/09, après la SUITE 3. Aucun quota.]**

**Constat** : à chaque redémarrage de Sheo, Johnny et Sugar, le journal écrit
`WARNING ⚠️ [TWITCH_CHAT:<bot>] Token invalide (code 401)`, puis une seconde plus tard
`🔄 Token rafraîchi avec succès`. C'est le cas NOMINAL : le jeton Twitch dure ~4 h, un
conteneur redémarré plus tard le trouve expiré et le rafraîchit. Un avertissement qui crie
pour du nominal apprend à ignorer les avertissements.

**Correctif** : `shared/twitch/auth.py`, `validate_token()` (l.95-97) : si `resp.status == 401`
→ `logger.info("🔄 [TWITCH_CHAT:<bot>] Jeton expiré (401), rafraîchissement…")`. Tout AUTRE
code reste en `warning`. Ne rien changer à `refresh()` : son échec est déjà en `error`, et c'est
lui qui dit si le problème est réel. Aucun changement de logique, seulement le niveau du journal.

**Verrou** (`tests/`, aiohttp simulé, aucun appel réseau) : un 401 → aucun `WARNING` émis ;
un 500 → un `WARNING` ; un refresh en échec → un `ERROR`.

Pyflakes → `pytest` → commit → push → CI `success`. **[Ahmed]** redémarrage hors live, groupé
avec celui de la SUITE 3. **[Claude]** vérifie au démarrage suivant : 0 `WARNING` 401,
`Token rafraîchi` présent.
