# -*- coding: utf-8 -*-
"""Verrou : l'enregistrement des commandes ne se rejoue pas a chaque RESUME.

`on_ready` refire a chaque reconnexion Discord. `setup_slash_commands` y pose
`@bot.tree.command(name="reputation")` : la 2e fois leve
`CommandAlreadyRegistered`, ce qui avorte le `try` **avant**
`await sync_slash_commands(bot)` — les commandes ne sont donc plus
resynchronisees de la session.

C'etait la source des 2 lignes `[SLASH] Erreur: Command 'reputation' already
registered.` du tableau de bord (johnny + onizuka, 09/06). Seul SugarBot avait
la garde ; les 5 autres l'ont recue le 11/09.

Cousin de [[bug-on-ready-taches-relancees]], qui avait ferme le meme trou pour
les `tasks.loop` (`.start()` sous `is_running()`) sans voir celui-ci.
"""

import ast
from pathlib import Path

import pytest

_RACINE = Path(__file__).resolve().parent.parent
_BOTS = {
    "Alfred": "Alfred/bot_alfred.py",
    "JohnnyBot": "JohnnyBot/bot_johnny.py",
    "MaiqBot": "MaiqBot/bot_maiq.py",
    "MalenaBot": "MalenaBot/bot_malena.py",
    "Sheogorath": "Sheogorath/bot_sheogorath.py",
    "SugarBot": "SugarBot/bot_sugar.py",
}
# Tout ce qui ENREGISTRE aupres de discord.py et ne tolere pas un second passage.
_ENREGISTREURS = ("setup_slash_commands", "setup_games")


def _on_ready(chemin):
    arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "on_ready":
            return arbre, n
    return arbre, None


def _gardes_englobantes(fonction, appel):
    """Rend les conditions de tous les `if` qui englobent `appel`."""
    conditions = []
    for n in ast.walk(fonction):
        if not isinstance(n, ast.If):
            continue
        lignes = [getattr(d, "lineno", -1) for d in ast.walk(n)]
        if n.lineno < appel.lineno <= max(lignes):
            conditions.append(n.test)
    return conditions


@pytest.mark.parametrize("nom,rel", sorted(_BOTS.items()))
def test_les_enregistreurs_sont_gardes_par_run_command_setup(nom, rel):
    arbre, ready = _on_ready(_RACINE / rel)
    assert ready is not None, f"{nom} ne declare pas on_ready"

    trouves = [
        s for s in ast.walk(ready)
        if isinstance(s, ast.Call) and isinstance(s.func, ast.Name)
        and s.func.id in _ENREGISTREURS
    ]
    assert trouves, f"{nom} : aucun enregistreur dans on_ready — liste a revoir ?"

    for appel in trouves:
        noms_gardes = {
            c.id for cond in _gardes_englobantes(ready, appel)
            for c in ast.walk(cond) if isinstance(c, ast.Name)
        }
        assert "run_command_setup" in noms_gardes, (
            f"{nom} : `{appel.func.id}` ligne {appel.lineno} n'est pas garde par "
            "`run_command_setup` — il se rejoue a chaque RESUME et leve "
            "CommandAlreadyRegistered."
        )


@pytest.mark.parametrize("nom,rel", sorted(_BOTS.items()))
def test_le_drapeau_est_pose_au_niveau_module_et_bascule_dans_on_ready(nom, rel):
    chemin = _RACINE / rel
    arbre, ready = _on_ready(chemin)

    au_module = any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_ready_setup_done" for t in n.targets)
        and isinstance(n.value, ast.Constant) and n.value.value is False
        for n in arbre.body
    )
    assert au_module, (
        f"{nom} : `_ready_setup_done = False` absent du niveau module — sans lui la "
        "garde est une variable locale, toujours vraie."
    )

    declare_global = any(
        isinstance(n, ast.Global) and "_ready_setup_done" in n.names
        for n in ast.walk(ready)
    )
    assert declare_global, f"{nom} : on_ready ne declare pas `global _ready_setup_done`"

    bascule = any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_ready_setup_done" for t in n.targets)
        and isinstance(n.value, ast.Constant) and n.value.value is True
        for n in ast.walk(ready)
    )
    assert bascule, (
        f"{nom} : on_ready ne pose jamais `_ready_setup_done = True` — la garde ne se "
        "refermerait jamais."
    )
