# PLAN — SUITE 19 : raccourcir les questions `!discord` de Sugar (LIVRAISON de la variante B)

Rédaction : Claude, le **2026-09-29** (réécrit le soir, après la mesure).
Exécution : **Antigravity**, sauf les étapes marquées **[Claude]** ou **[Ahmed]**.
Plans précédents : SUITES 14 et 15 → `483068c:PLAN.md` ; version mesure de la SUITE 19 → `25adb29:PLAN.md`.

## ⚠️ À LIRE AVANT DE COMMENCER

- **La mesure est FAITE** (LOT 1, par Claude). **Ne relance AUCUNE sonde**, aucun appel API.
- **UN SEUL fichier de code change** : `shared/twitch/dispatch.py`. **UN SEUL fichier de test
  change** : `tests/test_phrase_de_lien_jeu_en_cours.py`. Rien d'autre (sauf ce PLAN.md en
  fin de LOT 6). Si tu te retrouves à modifier un 3e fichier, **arrête-toi et dis-le**.
- `dispatch.py` **n'est pas** dans `tools/vendor_core.py` : **ne lance pas** le vendoring.
- **Aucun redémarrage de conteneur.** Le LOT 5 appartient à Ahmed.
- **Ne lance jamais deux `pytest` en même temps** (port 8599 partagé).
- Ne touche à aucun `.env`, `.master_key`, `*.db`.
- **PIÈGE** : la ligne `"Un emoji peut la finir. "` existe **DEUX fois** dans `dispatch.py` :
  - **l.907** : fin de `CLAUSES_JEU_PAR_BOT["sugar"]` ← **c'est CELLE-LÀ**
  - **l.964** : fin de `CLAUSES_FORME_JEU_PAR_BOT["johnny"]` ← **NE PAS TOUCHER**

---

## POURQUOI (résumé de la mesure, 29/09 ~16:30 UTC, 18 générations par bras)

| critère | A (prod) | B (à livrer) |
|---|---|---|
| question < 80 car. | 7/18 | **15/17** |
| titre complet du jeu dans la question | 12/18 | **0/17** |
| tutoiement | 2/18 | 0/17 |
| invitation qui nomme Discord | 18/18 | 17/17 |
| médiane de la question `designer` / `choix` | 102 / 89 car. | **62 / 63 car.** |
| médiane `chiffre` (inchangé, témoin) | 74,5 | 74 |
| 1er mot le plus fréquent | 11 « combien » | 9 « combien » |
| même question mot pour mot | 2× | 2× |

Les deux dernières lignes échouent aux seuils du plan, **mais elles échouent déjà en prod,
en pire** : B ne les crée pas. « Combien » sera traité dans une SUITE à part.
Sorties brutes : scratchpad de la session Claude `dc6cea00…` (`s19_A2.txt`, `s19_B2.txt`).

---

# LOT 1 — [Claude] Mesure A/B — ✅ FAIT (`25adb29`)

# LOT 2 — [Claude] Verdict — ✅ FAIT : livrer B, sous réserve de l'accord d'Ahmed

# LOT 3 — Le code : TROIS remplacements dans `shared/twitch/dispatch.py`

Faire **exactement** ces remplacements, caractère pour caractère. Les guillemets `« »` sont
entourés d'**espaces ordinaires** (U+0020), pas insécables : c'est ce qui a été mesuré.

### 3.1 — type `choix` (vers la l.934)

AVANT :
```python
            ("choix", "Cette fois, ta question, toujours au VOUVOIEMENT, les fait CHOISIR entre deux choses de ce jeu."),
```
APRÈS :
```python
            ("choix", "Cette fois, ta question, toujours au VOUVOIEMENT, les fait choisir entre deux choses de ce jeu, chacune dite en deux ou trois mots."),
```

### 3.2 — type `designer` (vers la l.935)

AVANT :
```python
            ("designer", "Cette fois, ta question, toujours au VOUVOIEMENT, leur demande de DÉSIGNER leur préféré parmi les personnages, les lieux ou les armes de ce jeu."),
```
APRÈS :
```python
            ("designer", "Cette fois, ta question, toujours au VOUVOIEMENT, leur demande leur personnage préféré de ce jeu."),
```

### 3.3 — type `chiffre` : **NE PAS TOUCHER** (témoin de la mesure)

L'ordre du tuple reste `choix`, `designer`, `chiffre` (le test de rotation existant en dépend).

### 3.4 — fin de la clause de Sugar (l.907, DANS `CLAUSES_JEU_PAR_BOT["sugar"]`)

AVANT (les deux dernières lignes du bloc `"sugar": (...)`) :
```python
            "Un emoji peut la finir. "
        ),
    }
```
APRÈS :
```python
            "Un emoji peut la finir. "
            "Dis « ce jeu » plutôt que son titre. "
        ),
    }
```
Vérifier que le bloc modifié est bien celui qui commence par `CLAUSES_JEU_PAR_BOT = {` et
contient `"Vouvoie le chat : ils sont plusieurs. "`. **Pas** `CLAUSES_FORME_JEU_PAR_BOT`.

### 3.5 — commentaire de mesure

Juste **au-dessus** de la ligne `TYPES_DE_QUESTION_JEU_PAR_BOT = {`, après le bloc
`# ⚠️ SUITE 8-ter …` existant (on garde tout l'historique), ajouter :

```python
    #
    # ⚠️ SUITE 19 (2026-09-29) : questions trop longues (22 réelles : 7/22 < 80 car.).
    # Causes : la phrase `designer` ÉNUMÉRAIT « personnages, lieux, armes » (recopiée par le
    # modèle), et le titre complet du jeu coûte 28 car. Une règle de VOLUME ne passe pas sur
    # flash-lite : on retire la liste, on borne `choix` en mots, et la clause dit « ce jeu ».
    # Mesure SUITE 19 (18 tirages par bras, Kingdom Come II, tête Gemini) :
    #   critère                            A (avant)      B (LIVRÉ)
    #   question < 80 car.                 7/18           15/17
    #   titre complet dans la question     12/18          0/17
    #   tutoiement                         2/18           0/17
    #   invitation nomme Discord           18/18          17/17
    #   médiane designer / choix           102 / 89 car.  62 / 63 car.
    #   médiane chiffre (inchangé, témoin) 74,5 car.      74 car.
    #   « combien » au 1er mot             11/18          9/17   (NON résolu, SUITE à part)
```

### 3.6 — contrôle immédiat

```bash
git diff --stat
```
Attendu : `shared/twitch/dispatch.py` seul, environ +18 / −2. Puis :
```bash
git diff shared/twitch/dispatch.py
```
Aucune ligne de `CLAUSES_FORME_JEU_PAR_BOT` ne doit apparaître dans le diff.

# LOT 4 — Les verrous : 5 tests AJOUTÉS à la fin de `tests/test_phrase_de_lien_jeu_en_cours.py`

**Ne modifier aucun test existant.** Réutiliser le `_faux_bot` du fichier. Les tests 4.4 et
4.5 passent par la **vraie** `_generate_link_line` (pas de logique recopiée dans le test).

```python
# ---------------------------------------------------------------------------
# SUITE 19 (2026-09-29) : questions plus courtes pour Sugar
# ---------------------------------------------------------------------------

def _types_sugar():
    return dict(DispatchMixin.TYPES_DE_QUESTION_JEU_PAR_BOT["sugar"])


def test_suite19_designer_ne_liste_plus_de_categories():
    """La phrase `designer` énumérait « personnages, lieux, armes » : le modèle recopiait
    la liste et la question dépassait 80 car. Elle ne demande plus qu'UNE catégorie."""
    phrase = _types_sugar()["designer"]
    assert "personnage préféré de ce jeu" in phrase
    for mot in ("les lieux", "les armes", "parmi", "DÉSIGNER"):
        assert mot not in phrase, f"« {mot} » est revenu dans la phrase designer : {phrase}"


def test_suite19_choix_borne_chaque_chose_en_mots():
    phrase = _types_sugar()["choix"]
    assert "chacune dite en deux ou trois mots" in phrase
    assert "VOUVOIEMENT" in phrase


def test_suite19_chiffre_est_inchange():
    """Témoin de la mesure : si on le touche, les chiffres de la SUITE 19 ne valent plus."""
    assert _types_sugar()["chiffre"] == (
        "Cette fois, ta question, toujours au VOUVOIEMENT, leur demande un CHIFFRE "
        "tiré de ce qu'ils y ont vécu."
    )
    assert [cle for cle, _ in DispatchMixin.TYPES_DE_QUESTION_JEU_PAR_BOT["sugar"]] == [
        "choix", "designer", "chiffre"
    ]


def test_suite19_sugar_recoit_ce_jeu_une_seule_fois():
    """Par le VRAI chemin : l'instruction envoyée au modèle pour Sugar avec un jeu contient
    la consigne « ce jeu » exactement une fois, juste après « Un emoji peut la finir. »."""
    bot = _faux_bot("sugar")
    bot._rang_type_question = 0

    async def faux_jeu():
        return "Kingdom Come: Deliverance II"
    bot._jeu_en_cours = faux_jeu

    captures = []

    async def faux_ecrire(instruction, system_prompt, cmd):
        captures.append(instruction)
        return "Venez nous en parler sur Discord !"
    bot._ecrire_phrase_de_lien = faux_ecrire

    res = asyncio.run(bot._generate_link_line("discord", "le serveur", "https://discord.gg/test"))
    assert res is not None
    consigne = "Dis « ce jeu » plutôt que son titre. "
    assert captures[0].count(consigne) == 1
    assert "Un emoji peut la finir. " + consigne in captures[0]


def test_suite19_johnny_ne_recoit_pas_ce_jeu():
    """La consigne est propre à Sugar : Johnny (même méthode, même jeu) ne la reçoit pas,
    et sa clause de forme n'a pas bougé."""
    assert "plutôt que son titre" not in DispatchMixin.CLAUSES_FORME_JEU_PAR_BOT["johnny"]

    bot = _faux_bot("johnny")

    async def faux_jeu():
        return "Kingdom Come: Deliverance II"
    bot._jeu_en_cours = faux_jeu

    captures = []

    async def faux_ecrire(instruction, system_prompt, cmd):
        captures.append(instruction)
        return "Venez nous en parler sur Discord !"
    bot._ecrire_phrase_de_lien = faux_ecrire

    res = asyncio.run(bot._generate_link_line("discord", "le serveur", "https://discord.gg/test"))
    assert res is not None
    assert "plutôt que son titre" not in captures[0]
```

### 4.1 — PREUVE que les verrous mordent (obligatoire, à coller dans le compte rendu)

Les tests doivent **échouer sur l'ancien code**. Mettre de côté SEULEMENT `dispatch.py` :

```bash
git stash push shared/twitch/dispatch.py
.venv/Scripts/python -m pytest tests/test_phrase_de_lien_jeu_en_cours.py -k suite19 -q
git stash pop
```

Résultat attendu sur l'ancien code, **à l'identique** :

| test | ancien code | nouveau code |
|---|---|---|
| `test_suite19_designer_ne_liste_plus_de_categories` | **FAIL** | pass |
| `test_suite19_choix_borne_chaque_chose_en_mots` | **FAIL** | pass |
| `test_suite19_chiffre_est_inchange` | pass | pass |
| `test_suite19_sugar_recoit_ce_jeu_une_seule_fois` | **FAIL** | pass |
| `test_suite19_johnny_ne_recoit_pas_ce_jeu` | pass | pass |

→ **3 failed, 2 passed** avant ; **5 passed** après. Un autre résultat = **s'arrêter et le dire**.
Après `git stash pop`, vérifier que `git diff --stat` montre de nouveau les deux fichiers.

# LOT 5 — Suite entière, commit, push, CI

```bash
.venv/Scripts/python -m pytest -q
```
Attendu : **0 failed** (pyflakes joue dans la suite). Coller la dernière ligne du résultat.

```bash
git add shared/twitch/dispatch.py tests/test_phrase_de_lien_jeu_en_cours.py
git commit -m "feat(sugar): questions !discord plus courtes — designer sans liste, choix borne, « ce jeu » (SUITE 19)"
git push
gh run list --limit 3
```
Attendre que le run du commit soit **completed / success** (`gh run watch` si besoin).
**Rouge = s'arrêter**, donner le lien du run et le log de l'échec, **ne rien corriger à l'aveugle**.

# LOT 6 — Compte rendu (Antigravity → Ahmed et Claude)

Donner, **brut** :
1. la sortie de `git diff --stat HEAD~1` ;
2. la sortie des tests `-k suite19` sur l'ANCIEN code (LOT 4.1) et sur le NOUVEAU ;
3. la dernière ligne de la suite entière ;
4. le hash du commit et l'état du run CI.

**Ne pas écrire « tout passe »** : recopier les sorties. Puis ajouter en bas de ce PLAN.md
une ligne `LOT 3–5 livrés : <hash>, CI <verte|rouge>`.

# LOT 7 — [Claude] Relecture

Relire le diff ligne à ligne et rejouer la preuve du LOT 4.1.

# LOT 8 — [Ahmed] Redémarrage de `bot-sugar` SEUL, hors live

```bash
docker restart bot-sugar
docker inspect -f "{{.State.StartedAt}}" bot-sugar
docker exec bot-sugar grep -c "plutôt que son titre" /app/shared/twitch/dispatch.py
docker logs bot-sugar --since 2m 2>&1 | grep -iE "error|traceback" 
```
Attendu : `StartedAt` = maintenant, grep = `1`, aucune erreur. Les autres conteneurs ne sont
**pas** relancés (leur `StartedAt` ne bouge pas). ⚠️ Le chemin `/app/shared/…` est à vérifier
par Claude avant le redémarrage (`docker exec bot-sugar ls /app`).

# LOT 9 — [Claude + Ahmed] Contrôle au prochain live de Sugar

Sur les ≥ 5 premières phrases `!discord` avec un jeu : question < 80 car. dans au moins 4,
titre complet du jeu dans aucune, vouvoiement partout, Discord nommé partout.
