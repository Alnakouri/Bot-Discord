# PLAN — La phrase de lien `!discord` : le tic du « XVe siècle », et la question de Sugar

Rédaction : Claude, le **2026-09-23**. Exécution : **Antigravity**, sauf les étapes marquées
**[Ahmed]**. Le plan précédent (audit du 22/09) est livré, sauf le LOT 7 et deux questions,
recopiés en fin de fichier. Il reste lisible dans git (`5d36894:PLAN.md`).

Un seul fichier touché dans le code : `shared/twitch/dispatch.py`. Il n'est **pas** vendoré :
`dispatch.py` n'est pas dans `MODULES` de `tools/vendor_core.py`, donc pas de
`vendor_core.py` à relancer. Il sert aux six bots, mais seuls ceux de `ACCROCHE_AU_JEU`
(`sugar`, `alfred`, `malena`, `johnny`) voient le changement 1, et Sugar seule le changement 2.

---

## CE QUI A ÉTÉ MESURÉ (23/09, `tools/sonde_phrase_de_lien.py`, KCD2, n = 18, Gemini)

La sonde appelle le vrai `_generate_link_line` de la prod ; `--fiche` impose la fiche IGDB
réelle de KCD2 (« …set in 15th century Medieval Europe… »).

| bot | siècle cité, sans fiche | siècle cité, AVEC fiche | autre effet de la fiche |
|---|---|---|---|
| alfred | 0/18 | **18/18** | débuts de phrase : 9 formes → **4** ; « La boue du quinzième siècle » **13/18** |
| malena | 0/18 | 16/18 | — |
| sugar | 0/18 | 14/18 | — |
| johnny | 0/18 | 14/18 | ✅ « Henri V » (faux) disparaît ; au-delà de 120 car. : 15/17 → **7/18** |

▶ **La date de la fiche devient un tic.** Même mécanisme que « Il semblerait »
([[gotcha-une-formule-nommee-devient-un-tic]]) : ce qu'on écrit dans le prompt ressort partout.
▶ **Le reste de la fiche est utile** : plus aucun fait inventé sur le jeu, Johnny raccourcit.
On retire donc **la date seulement**, pas la fiche.

**Sugar + clause « question aux lecteurs »** (demande d'Ahmed : « Vous galérez autant en
Bohême que Henry ? venez nous partager ça »), clause injectée par `--clause`, avec fiche :

| | sans la clause | avec la clause |
|---|---|---|
| question sur l'expérience DES LECTEURS + invitation à la raconter | ~0/18 | **~13/18** ✅ |
| contenu du Discord inventé (« nos débats », « on discute de chevalerie là-bas ») | 3/18 | **0/18** ✅ |
| longueur médiane | 112 car. | **176 car.** ❌ |
| au-delà de 120 car. | 5/17 | **17/18** ❌ |
| sans invitation du tout | 0 | 2 (#2, #6) ❌ |
| question sur Henry au lieu des lecteurs | — | 2 (#9, #18) ❌ |

▶ **L'intention passe, la longueur non.** La clause mesurée demandait deux choses (poser une
question PUIS inviter) dans une phrase de 120 caractères : le modèle a fait deux phrases
collées. La nouvelle version exige que les deux tiennent dans la même phrase courte.

---

# LOT 1 — La fiche est donnée au modèle SANS sa date

## 1.1 — Nouvelle fonction `_fiche_sans_epoque`

Dans `shared/twitch/dispatch.py`, **juste après `_siecles_de_la_fiche`** (fin l.138), ajouter :

```python
# Ce qu'on retire de la fiche AVANT de la donner au modele — et SEULEMENT a lui.
# ⚠️ Le siecle SEUL, sans sa preposition : « set in 15th century Medieval Europe » doit
# devenir « set in Medieval Europe », pas « set Medieval Europe ». L'annee, AVEC sa
# preposition (et sa virgule) : « In 1403, Henry… » -> « Henry… ». Une annee nue n'est pas
# retiree : « Over 1000 quests » n'est pas une date.
_EPOQUE_DE_LA_FICHE = re.compile(
    r"\s*\b\d{1,2}(?:st|nd|rd|th)[- ]century\b"
    r"|\s*\b(?:in|since|from|during)\s+1\d{3}\b,?",
    re.I,
)


def _fiche_sans_epoque(fiche: str | None) -> str | None:
    """La fiche IGDB sans ses siecles ni ses annees, pour l'INSTRUCTION du modele.

    ⚠️ Mesure du 2026-09-23 (KCD2, n=18, Gemini) : avec « 15th century » dans la fiche, le
    siecle sort dans 18/18 phrases d'Alfred, 16/18 de Malena, 14/18 de Sugar et de Johnny,
    contre 0/18 sans fiche. Les ouvertures d'Alfred passent de 9 formes a 4. Une date
    ecrite dans le prompt devient un tic ([[gotcha-une-formule-nommee-devient-un-tic]]).
    Le reste de la fiche est garde : il fait disparaitre les faits inventes (« Henri V »).

    ⚠️ Le FILET, lui, recoit la fiche COMPLETE (`_affirme_une_epoque(phrase, jeu, fiche)`) :
    si le modele cite quand meme le XVe siecle de sa memoire, c'est juste, et ca passe.
    """
    if not fiche:
        return fiche
    propre = _EPOQUE_DE_LA_FICHE.sub("", fiche)
    return " ".join(propre.split()).replace(" ,", ",").replace(" .", ".")
```

⚠️ **Piège à éviter** : ne PAS mettre ce nettoyage dans `_fiche_du_jeu` (l.748) ni dans
`fiche_courte` (`shared/twitch/game_info.py:337`). La variable `fiche` de
`_generate_link_line` doit rester complète, parce qu'elle est aussi passée au filtre
l.1015 : `_affirme_une_epoque(phrase, jeu, fiche)`. Si le filtre reçoit la fiche sans date,
« XVe siècle » (juste) redevient un rejet → gabarit fixe, soit le défaut corrigé par
`70aacb1`. Et `fiche_courte` sert aussi ailleurs.

## 1.2 — Brancher dans l'instruction

`shared/twitch/dispatch.py:992-996`, **avant** :

```python
            if fiche:
                instruction += (
                    f"Voici la fiche officielle de ce jeu (en anglais) : {fiche}. "
```

**après** :

```python
            if fiche:
                instruction += (
                    f"Voici la fiche officielle de ce jeu (en anglais) : {_fiche_sans_epoque(fiche)}. "
```

La ligne suivante (« C'est TOUT ce que tu sais de vrai… ») ne change pas. Rien d'autre ne
bouge : l.1015 garde `fiche`.

## 1.3 — Tests

**a) Un test existant CASSE, c'est voulu** : `tests/test_phrase_de_lien_jeu_en_cours.py:184`
affirme `"15th century RPG" in capture["instruction"]`. Le remplacer par :

```python
    assert "RPG" in capture["instruction"]
    # ⚠️ La date de la fiche ne va plus au modele : elle devenait un tic (23/09).
    assert "15th century" not in capture["instruction"]
```

**b) Nouveau**, dans `tests/test_phrase_de_lien_seconde_chance.py` (qui a déjà `FICHE_KCD2`
l.126), après `test_une_epoque_JUSTE_passe_au_premier_essai_quand_la_fiche_la_donne` :

```python
@pytest.mark.parametrize("fiche,absent,present", [
    (FICHE_KCD2, "15th century", "set in Medieval Europe"),
    ("Résumé : In 1403, Henry seeks revenge. | Thèmes : Action", "1403", "Résumé : Henry seeks revenge"),
    ("Résumé : Bohemia in 1403 is torn by war.", "1403", "Bohemia is torn by war"),
    ("Résumé : Set during the 13th-century wars.", "13th", "Set during the wars"),
])
def test_la_fiche_du_MODELE_perd_sa_date(fiche, absent, present):
    from shared.twitch.dispatch import _fiche_sans_epoque
    propre = _fiche_sans_epoque(fiche)
    assert absent not in propre and present in propre


def test_une_fiche_sans_date_ne_bouge_pas():
    from shared.twitch.dispatch import _fiche_sans_epoque
    assert _fiche_sans_epoque(None) is None
    assert _fiche_sans_epoque("Résumé : A space RPG. | Thèmes : Sci-fi") == \
        "Résumé : A space RPG. | Thèmes : Sci-fi"
    # une annee NUE n'est pas une date : elle reste
    assert _fiche_sans_epoque("Résumé : Over 1000 quests.") == "Résumé : Over 1000 quests."
```

⚠️ **Le test de bout en bout existant DOIT rester vert sans être modifié** :
`test_une_epoque_JUSTE_passe_au_premier_essai_quand_la_fiche_la_donne` (l.154). C'est lui
qui prouve que le filtre reçoit encore la fiche complète. S'il casse, c'est que le piège de
1.1 a été commis.

---

# LOT 2 — Sugar pose une question aux lecteurs, EN UNE phrase courte

## 2.1 — Une table de clauses qui ne s'applique QU'AVEC un jeu

La clause parle de « ce jeu » : hors live ou en « Just Chatting », elle n'a pas de sens.
Elle ne va donc **pas** dans `CLAUSES_PAR_BOT` (qui s'applique toujours, l.975) mais dans
une nouvelle table, lue dans le bloc `if jeu:`.

Dans `shared/twitch/dispatch.py`, **juste après `ACCROCHE_AU_JEU = {…}`** (l.712), ajouter :

```python
    # Clauses ajoutees POUR UN SEUL BOT, et SEULEMENT quand un jeu est diffuse : elles
    # parlent de « ce jeu », et hors live elles n'auraient pas de sens.
    #
    # ⚠️ SUGAR — demande d'Ahmed le 2026-09-23 : qu'elle interroge les lecteurs sur LEUR
    # experience du jeu (« Vous galerez autant en Boheme que Henry ? venez nous partager
    # ca »). Sans exemple dans le texte : une formule citee devient un tic.
    # Premiere version mesuree le 23/09 (KCD2 + fiche, n=18, Gemini) :
    #     question aux lecteurs + invitation ... ~13/18   (contre ~0 sans)
    #     contenu du Discord invente ..........   0/18   (contre 3/18)
    #     longueur mediane ....................  176 car. (contre 112)  <- REFUSE
    #     au-dela de 120 car. .................  17/18
    # Elle demandait « une question PUIS une invitation » : le modele collait deux
    # phrases. Cette version-ci exige que les deux tiennent dans UNE phrase courte.
    CLAUSES_JEU_PAR_BOT = {
        "sugar": (
            "⚠️ Adresse-toi à ceux qui LISENT, pas au personnage du jeu : ta phrase est "
            "UNE question sur ce que CE JEU leur a fait vivre, à eux, quand ils y ont "
            "joué — jamais sur la partie en cours, jamais une pique sur eux — et cette "
            "même question les invite à venir le raconter là-bas. Question et invitation "
            "tiennent dans la MÊME phrase, sous les 120 caractères : pas de mise en scène "
            "avant, pas de seconde phrase après. "
        ),
    }
```

## 2.2 — La lire dans le bloc `if jeu:`

`shared/twitch/dispatch.py:992-1000` : insérer **entre** la fin du bloc `if fiche:`
(l.996) et `instruction += (f"⚠️ Et ta phrase doit CLAQUER…` (l.997) :

```python
            instruction += self.CLAUSES_JEU_PAR_BOT.get(self.bot_id, "")
```

⚠️ Même indentation que `if fiche:` (12 espaces, dans `if jeu:`), **pas** dans le `if fiche:` :
la question vaut aussi quand IGDB est muet.

## 2.3 — Tests

Dans `tests/test_phrase_de_lien_jeu_en_cours.py`, sur le modèle de
`test_instruction_inclut_la_fiche_si_disponible` (l.166) : un faux bot, un faux
`_ecrire_phrase_de_lien` qui capture l'instruction. Trois cas :

1. `sugar` + jeu → `CLAUSES_JEU_PAR_BOT["sugar"]` est dans l'instruction ;
2. `sugar` **sans** jeu (`_jeu_en_cours` rend `None`) → elle n'y est **pas** ;
3. `alfred` + jeu → elle n'y est **pas**.

Comparer au texte de la table (`DispatchMixin.CLAUSES_JEU_PAR_BOT["sugar"]`), pas à une
copie retapée dans le test ([[gotcha-test-qui-retape-la-logique]]).

---

# LOT 3 — Vérifier, dans cet ordre

1. `python -m pyflakes shared/twitch/dispatch.py tests/test_phrase_de_lien_*.py`
2. La suite complète, **un seul pytest à la fois** (port 8599) :
   `uv run --no-project --python 3.11 --with-requirements requirements.txt -- python -m pytest -q`
   Attendu : tout vert (1329 + les nouveaux).
3. Commit, push, puis **`gh run list --limit 1` → `success`**. Rien n'est livré avant.

---

# LOT 4 — Mesure AVANT la prod **[Antigravity ou Claude, quota de prod : jamais pendant un live]**

Même protocole que le 23/09, pour comparer à l'identique (la sonde appelle le code de prod,
donc elle mesure les LOTS 1 et 2 sans `--clause`) :

```bash
FICHE="Résumé : A thrilling story-driven action RPG, with a rich open world, set in 15th century Medieval Europe. Experience the ultimate medieval adventure - through the eyes of young Henry - as you embark on a journey of epic proportions. | Thèmes : Action, Historical, Open world"
for b in sugar alfred malena johnny; do
  PYTHONIOENCODING=utf-8 uv run --no-project --python 3.11 --with-requirements requirements.txt -- \
    python tools/sonde_phrase_de_lien.py --bot $b --jeu "Kingdom Come: Deliverance II" \
    --fiche "$FICHE" --n 18 --pause 5 > mesure_${b}.txt 2>&1
done
```

(fichiers de sortie dans un dossier temporaire, **jamais commités**)

**Critères fixés MAINTENANT, avant de voir les chiffres :**

| critère | seuil | aujourd'hui |
|---|---|---|
| siècle cité (XVe, quinzième, 15e) | **≤ 4/18** pour chaque bot | 14 à 18/18 |
| repli sur le gabarit fixe | ≤ 2/18 par bot | 0 à 1/18 |
| débuts de phrase distincts, Alfred | **≥ 8** | 4 |
| Sugar : longueur médiane | **≤ 130 car.** | 176 |
| Sugar : question aux lecteurs + invitation, dans la même phrase | **≥ 12/18** (lecture phrase par phrase) | ~13/18 |
| Sugar : question sur Henry au lieu des lecteurs | ≤ 2/18 | 2/18 |
| faits inventés sur le jeu (dates, noms, « bugs de sauvegarde ») | ≤ 1/18 par bot | 1 (Sugar) |

⚠️ **À surveiller, sans seuil** : « Medieval Europe » reste dans la fiche. Si « médiéval »
ou « Moyen Âge » devient le nouveau tic (≥ 12/18), le noter : le problème serait alors le
fait de NOMMER une époque, pas le siècle.

⚠️ Plancher de bruit à n = 18 : environ ±3/18 ([[gotcha-plancher-de-bruit-du-harnais]]).
Un écart plus petit que ça n'est pas un résultat.

**Décision :**
- tout passe → LOT 5 ;
- LOT 1 passe mais pas Sugar → livrer le LOT 1 seul (retirer l'entrée `sugar` de
  `CLAUSES_JEU_PAR_BOT`, **garder la table vide** et ses tests 2 et 3), et rapporter à Ahmed ;
- le LOT 1 échoue → ne rien déployer, rapporter les chiffres.

---

# LOT 5 — Prod **[Ahmed : hors live]**

`dispatch.py` est chargé au démarrage (montage lié, modules déjà importés) :
`docker restart bot-sugar bot-alfred bot-malena bot-johnny`. Pas de rebuild, aucune
dépendance ne bouge. Vérifier dans `docker logs --since 5m <bot>` la ligne « Twitch
connecté », puis au prochain live un `!discord` sur `#ma_streameuse` : la ligne
`✨ … Phrase de lien !discord (jeu : …) écrite par le bot` donne la phrase réelle.

---

## RESTE DU PLAN PRÉCÉDENT (22/09)

- **LOT 7 [Ahmed]** — recréer `.venv` en 3.11 (aujourd'hui 3.13 sans pyflakes) :
  `uv venv --python 3.11 .venv` puis
  `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`.
- **Questions ouvertes** : (1) Sheogorath réagit par emoji aux messages des AUTRES bots
  (`bot_sheogorath.py`, réactions avant la garde `author.bot`) — voulu ? (2) la borne de
  300 ms de Laya.
- Petite dette : `610fdac` pose un attelage factice par `setdefault` sur
  `runner._ATTELAGES` sans le retirer (fuite d'état entre tests ; `monkeypatch` serait propre).

## INTERDITS DE CE PLAN

- Aucun `.env`, `.master_key`, `.env.encrypted`, ni base de `data/` touché.
- Aucune clé d'un bot utilisée pour un autre : la sonde charge les clés du bot mesuré
  depuis son propre dossier, ne pas contourner.
- Aucun import entre bots ; aucune factorisation.
- Ne pas toucher à `fiche_courte`, `_fiche_du_jeu`, ni au filtre `_affirme_une_epoque`.
- **Un seul `pytest` à la fois.** Aucun lot « livré » tant que la CI n'est pas `success`.
