# -*- coding: utf-8 -*-
"""Verrou SUITE 18 : le rattrapage des mentions manquees tourne UNE fois par connexion.

Mesure du 2026-09-28 : de 22/09 au 28/09, `check_missed_mentions_sheo` et
`check_missed_mentions_malena` relisaient toutes les 2 min les 20 derniers messages de
CHAQUE salon, et n'ont rattrape AUCUNE mention (0 ligne `MENTION MANQUEE`). `on_message`
repond deja en direct ; le seul cas utile est la mention tombee pendant une deconnexion.

La boucle devient `@tasks.loop(count=1)`, et `on_ready` la relance a chaque connexion.
Deux facons de casser ca sans s'en apercevoir, verrouillees ici :
- remettre un intervalle (`minutes=`, `seconds=`, `hours=`) : la charge revient ;
- deplacer le `.start()` dans le bloc « une seule fois » d'`on_ready` : apres une
  reconnexion, plus rien ne rattrape les mentions tombees pendant la coupure.
"""
import ast
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
CAS = [
    ("Sheogorath/bot_sheogorath.py", "check_missed_mentions_sheo"),
    ("MalenaBot/bot_malena.py", "check_missed_mentions_malena"),
]


def _arbre(rel):
    chemin = RACINE / rel
    return ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))


def _fonction(arbre, nom):
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return n
    raise AssertionError(f"{nom} introuvable")


@pytest.mark.parametrize("rel,nom", CAS, ids=[c[1] for c in CAS])
def test_la_boucle_ne_tourne_qu_une_fois(rel, nom):
    fonction = _fonction(_arbre(rel), nom)
    boucles = [d for d in fonction.decorator_list
               if isinstance(d, ast.Call) and getattr(d.func, "attr", None) == "loop"]
    assert len(boucles) == 1, f"{nom} n'est plus une tasks.loop"
    mots = {k.arg: k.value for k in boucles[0].keywords}
    # Sans `count=1`, l'intervalle redevient une vraie cadence : la relecture de chaque
    # salon toutes les 2 min revient.
    assert "count" in mots, f"{nom} n'a plus `count=` : elle tourne de nouveau en continu"
    assert isinstance(mots["count"], ast.Constant) and mots["count"].value == 1
    # Et un intervalle NON nul, sinon `core.boucles` crie « 0 s de retard » a chaque
    # demarrage (constate le 29/09 au premier deploiement).
    assert set(mots) & {"seconds", "minutes", "hours"}, (
        f"{nom} : count=1 sans intervalle = fausse alerte de rattrapage au demarrage"
    )


@pytest.mark.parametrize("rel,nom", CAS, ids=[c[1] for c in CAS])
def test_on_ready_la_relance_a_chaque_connexion(rel, nom):
    """Le `.start()` doit etre dans `on_ready`, HORS du bloc `if run_command_setup`."""
    on_ready = _fonction(_arbre(rel), "on_ready")
    starts = [n for n in ast.walk(on_ready)
              if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "start"
              and getattr(n.func.value, "id", None) == nom]
    assert starts, f"on_ready ne demarre plus {nom}"

    blocs_une_fois = [n for n in ast.walk(on_ready) if isinstance(n, ast.If)
                      and "run_command_setup" in ast.unparse(n.test)]
    for bloc in blocs_une_fois:
        for s in starts:
            assert not any(s is x for x in ast.walk(bloc)), (
                f"{nom}.start() est dans le bloc « une seule fois » d'on_ready : "
                "une reconnexion ne rattraperait plus rien"
            )
