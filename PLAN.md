# PLAN — Les réactions emoji de Sheogorath : aux humains seulement, sur des mots entiers

Rédaction : Claude, le **2026-09-23**. Exécution : **Antigravity**, sauf les étapes marquées
**[Ahmed]**. Décision d'Ahmed (option 3 de trois proposées) : Sheogorath ne réagit plus
qu'aux messages des HUMAINS, et seulement sur des mots ENTIERS. Le plan précédent (bio
Twitch de Johnny) est livré (`5e45377`, CI verte, vérifié en prod à 16:13) ; lisible dans
git (`5e45377:PLAN.md`).

Un seul fichier de code : `Sheogorath/bot_sheogorath.py`. Aucun `shared/`, rien à vendorer.

---

## CE QUI A ÉTÉ CONSTATÉ (23/09)

`Sheogorath/bot_sheogorath.py:1878-1897`, dans `on_message` :

```python
    # 1. AUTO-REACTIONS (Ajoute des emojis selon les mots-clés)
    reactions_map = {
        "fromage": "🧀", "cheese": "🧀", "roquefort": "🧀", "brie": "🧀",
        ...
        "sang": "🩸", "entrailles": "🥩"
    }
    msg_lower = message.content.lower()
    for word, emoji in reactions_map.items():
        if word in msg_lower:
            ...await message.add_reaction(emoji)...

    # SILENCE TOTAL ENTRE BOTS — un bot ne répond JAMAIS à un autre bot.
    if message.author.bot:
        return
```

1. **Les réactions passent AVANT la garde `author.bot`** : Sheogorath réagit aux messages
   des cinq autres bots (seuls les siens sont exclus, l.1858). Exemple : chaque « Wesh le
   sang » de Malena reçoit 🩸.
2. **`word in msg_lower` cherche une SOUS-CHAÎNE** : « Gabriel » contient `brie` → 🧀,
   « désordre » contient `ordre` → ⚖️.
3. Un message qui dit « fromage » et « brie » reçoit 🧀 deux fois (Discord l'ignore, mais
   c'est un appel réseau pour rien).

---

# LOT 1 — La table et la détection sortent de `on_message`, en mots entiers

## 1.1 — Au niveau du module

Dans `Sheogorath/bot_sheogorath.py`, **juste avant** `async def _other_bot_in_focus(message):`
(l.1839), ajouter :

```python
# Les reactions emoji de Sheogorath, par MOT ENTIER (un « s » final accepte).
# ⚠️ 23/09 : la recherche par SOUS-CHAINE faisait reagir a « Gabriel » (brie -> 🧀) et a
# « desordre » (ordre -> ⚖️). Et elle passait AVANT la garde `author.bot` : chaque « wesh
# le sang » de Malena recevait 🩸. Decision d'Ahmed : aux humains seulement, mots entiers.
REACTIONS_MOTS = {
    "fromage": "🧀", "cheese": "🧀", "roquefort": "🧀", "brie": "🧀",
    "folie": "🤪", "démence": "🧠", "madness": "🤪",
    "wabbajack": "✨", "jyggalag": "⚖️", "ordre": "⚖️",
    "haskill": "👔", "papillon": "🦋", "butterfly": "🦋",
    "sang": "🩸", "entrailles": "🥩",
}
_MOTIFS_REACTIONS = {
    mot: re.compile(rf"\b{re.escape(mot)}s?\b") for mot in REACTIONS_MOTS
}


def _emojis_des_mots(texte: str) -> list[str]:
    """Les emojis a poser sur ce texte, sans doublon, dans l'ordre de la table."""
    bas = (texte or "").lower()
    return list(dict.fromkeys(
        REACTIONS_MOTS[mot] for mot, motif in _MOTIFS_REACTIONS.items() if motif.search(bas)
    ))
```

⚠️ `re` est déjà importé (l.19). `\b` de Python est Unicode : « démence » est un mot entier.
⚠️ La table est **recopiée à l'identique** de l'actuelle (mêmes 15 mots, mêmes emojis) :
ne rien ajouter ni retirer, ce n'est pas l'objet du plan.

## 1.2 — Dans `on_message` : supprimer l'ancien bloc, le remettre APRÈS la garde

**Avant** (l.1878-1897) : le bloc cité plus haut, du commentaire
`# 1. AUTO-REACTIONS` jusqu'au `return` de `if message.author.bot:`.

**Après** :

```python
    # SILENCE TOTAL ENTRE BOTS — un bot ne répond JAMAIS à un autre bot.
    # ⚠️ Ni par emoji : les reactions viennent APRES cette garde (23/09).
    if message.author.bot:
        return

    # 1. AUTO-REACTIONS (emojis sur des mots ENTIERS, messages humains seulement)
    for emoji in _emojis_des_mots(message.content):
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException as e:
            logger.debug(f"[REACTION] emoji refuse par Discord : {e}")
```

La ligne suivante reste `# Gestion des mentions ou réponses` / `is_mentioned = ...`.

⚠️ **Piège** : ne pas laisser l'ancien `reactions_map` ni la boucle `if word in msg_lower`
en place « en plus ». Après le lot, `grep -n "reactions_map" Sheogorath/bot_sheogorath.py`
ne rend **rien**.
✅ Supprimer le `msg_lower = message.content.lower()` de l.1887 est sûr : vérifié le 23/09,
`on_message` le **redéfinit** l.1907 avant tout autre usage (l.1908 et suivantes). Garder
celui de l.1907.

---

# LOT 2 — Tests : nouveau `tests/test_reactions_sheogorath.py`

Le fichier du bot n'est pas importé dans les tests (trop lourd) : on le lit en AST, comme
`tests/test_classement_sans_bots.py:143`. On **n'écrit pas** une copie de la fonction
dans le test : on exécute celle du fichier.

```python
import ast
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CHEMIN = RACINE / "Sheogorath" / "bot_sheogorath.py"
SOURCE = CHEMIN.read_text(encoding="utf-8")
ARBRE = ast.parse(SOURCE, filename=str(CHEMIN))


def _charger():
    """Execute REACTIONS_MOTS, _MOTIFS_REACTIONS et _emojis_des_mots DU FICHIER DU BOT."""
    noeuds = [n for n in ARBRE.body
              if (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in
                  ("REACTIONS_MOTS", "_MOTIFS_REACTIONS") for t in n.targets))
              or (isinstance(n, ast.FunctionDef) and n.name == "_emojis_des_mots")]
    assert len(noeuds) == 3, "table, motifs ou fonction introuvables au niveau du module"
    espace = {"re": re}
    exec(compile(ast.Module(body=noeuds, type_ignores=[]), str(CHEMIN), "exec"), espace)
    return espace["_emojis_des_mots"]
```

Cas (paramétrés) :

| texte | attendu |
|---|---|
| `"J'adore le fromage"` | `["🧀"]` |
| `"Des fromages et du brie"` | `["🧀"]` (un seul, pas deux) |
| `"Gabriel est là"` | `[]` |
| `"Quel désordre"` | `[]` |
| `"L'ORDRE de Jyggalag"` | `["⚖️"]` (un seul) |
| `"Wesh le sang"` | `["🩸"]` (mot entier : attendu, c'est la décision) |
| `"sanglier"` | `[]` |
| `"La démence !"` | `["🧠"]` |
| `""` et `None` | `[]` |

Et **le verrou d'ordre**, sur le corps d'`on_message` :

```python
def test_les_reactions_viennent_APRES_la_garde_des_bots():
    fn = next(n for n in ast.walk(ARBRE)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_message")
    lignes_garde = [n.lineno for n in ast.walk(fn)
                    if isinstance(n, ast.If) and ast.unparse(n.test) == "message.author.bot"]
    lignes_reaction = [n.lineno for n in ast.walk(fn)
                       if isinstance(n, ast.Attribute) and n.attr == "add_reaction"]
    assert lignes_garde and lignes_reaction
    assert min(lignes_garde) < min(lignes_reaction), \
        "une reaction est posee AVANT la garde author.bot : Sheogorath reagit aux autres bots"
```

⚠️ `ast.unparse(n.test) == "message.author.bot"` vise le `if message.author.bot:` **nu**
(les autres, `if not message.author.bot and ...`, ne correspondent pas). S'il n'y en a
qu'un, c'est celui du lot 1.2. Et le test doit **casser** sur le code d'aujourd'hui :
le lancer une fois AVANT le lot 1.2 pour le voir rouge.

---

# LOT 3 — Vérifier, dans cet ordre

1. `python -m pyflakes Sheogorath/bot_sheogorath.py tests/test_reactions_sheogorath.py`
2. La suite complète, **un seul pytest à la fois** (port 8599) :
   `uv run --no-project --python 3.11 --with-requirements requirements.txt -- python -m pytest -q`
   Attendu : tout vert.
3. Commit, push, puis **`gh run list --limit 1` → `success`**. Rien n'est livré avant.

---

# LOT 4 — Prod **[Ahmed : hors live]**

`docker restart bot-sheogorath` (lui seul). `docker logs --since 5m bot-sheogorath` : la
connexion Discord, aucune `Traceback`. Test à la main sur Discord : un humain écrit
« du fromage » → 🧀 ; « Gabriel » → rien ; un message d'un autre bot contenant « folie »
→ rien.

---

## RESTE DES PLANS PRÉCÉDENTS

- **LOT 7 du 22/09 [Ahmed]** — recréer `.venv` en 3.11 (aujourd'hui 3.13 sans pyflakes) :
  `uv venv --python 3.11 .venv` puis
  `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`.
- **Question ouverte** : la borne de 300 ms de Laya (Laya est GARDÉ, décision d'Ahmed du 23/09).
- **À lire après le live du 23/09 au soir** : les lignes
  `Phrase de lien !discord (jeu : …) écrite par le bot` de Sugar et Johnny (première
  mesure réelle de `2bb82b5`) ; le tic « boue / médiéval » n'est à traiter que s'il se voit.
- ~~Dette `runner._ATTELAGES`~~ : déjà soldée (`tests/test_eval_harness.py:810-820`,
  `monkeypatch.setitem`).

## INTERDITS DE CE PLAN

- Aucun `.env`, `.master_key`, `.env.encrypted`, ni base de `data/` touché.
- Aucun import entre bots ; aucune factorisation (la table reste DANS le fichier de Sheogorath).
- Ne pas changer la liste des mots ni des emojis.
- **Un seul `pytest` à la fois.** Aucun lot « livré » tant que la CI n'est pas `success`.
