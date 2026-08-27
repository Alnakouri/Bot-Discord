# -*- coding: utf-8 -*-
"""Tout le code qui tourne est-il bien DANS le dépôt ?

Le 2026-08-26, `.gitignore` contenait `test_*.py` sans « / » initial. La règle
visait les scripts jetables de la racine ; sans ancrage, git l'applique à tous les
niveaux. Elle a donc avalé `shared/test_mode.py` — le module qui empêche les bots
de publier ailleurs que sur le serveur privé.

Rien ne l'a signalé pendant quatre commits : le fichier existait en local, les bots
tournent sur un bind mount local, et les 415 tests passaient. Les bots l'importent
sous `try/except ImportError` (règle « bots indépendants ») : sur un clone frais,
le garde-fou n'aurait pas planté, il aurait simplement **disparu en silence**.

D'où ce test. Il ne coûte rien et il ferme la classe entière de la panne : un
fichier source non suivi par git est un fichier qui n'existe pas pour les autres.
"""
import subprocess
from pathlib import Path

import pytest

_racine = Path(__file__).resolve().parent.parent

# Répertoires dont le contenu Python DOIT être livré. On ne balaie pas la racine :
# c'est là que vivent les scripts ad-hoc que `.gitignore` a le droit d'écarter.
_DOSSIERS_LIVRES = (
    "shared",
    "tools",
    "tests",
    "dashboard/backend",
    "Alfred",
    "JohnnyBot",
    "MaiqBot",
    "MalenaBot",
    "Sheogorath",
    "SugarBot",
)


def _fichiers_suivis():
    try:
        sortie = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=_racine, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        pytest.skip(f"git indisponible : {e}")
    if sortie.returncode != 0:
        pytest.skip("pas un dépôt git")
    return {c for c in sortie.stdout.split("\0") if c}


def test_aucun_module_source_n_echappe_au_depot():
    suivis = _fichiers_suivis()
    manquants = []
    for dossier in _DOSSIERS_LIVRES:
        base = _racine / dossier
        if not base.is_dir():
            continue
        for f in base.rglob("*.py"):
            if "__pycache__" in f.parts:
                continue
            chemin = f.relative_to(_racine).as_posix()
            if chemin not in suivis:
                manquants.append(chemin)

    assert not manquants, (
        "des fichiers Python ne sont pas suivis par git — ils n'existent que sur "
        "cette machine :\n  " + "\n  ".join(sorted(manquants)) +
        "\n\nSoit ils doivent être commités (`git add`), soit `.gitignore` les "
        "écarte à tort : vérifier avec `git check-ignore -v <fichier>`."
    )


def test_les_regles_de_scripts_jetables_sont_ancrees_a_la_racine():
    """La cause racine, verrouillée à la source.

    `test_*.py` s'applique partout ; `/test_*.py` seulement à la racine. La seconde
    forme est la seule qui dise ce que la règle voulait dire.
    """
    lignes = (_racine / ".gitignore").read_text(encoding="utf-8").splitlines()
    fautives = []
    for ligne in lignes:
        regle = ligne.strip()
        if not regle or regle.startswith("#") or regle.startswith("!"):
            continue
        if regle.startswith("/") or "/" in regle.rstrip("/"):
            continue          # déjà ancrée, ou chemin explicite
        nom = regle.rstrip("/")
        if nom.startswith(("test_", "check_")) or nom.endswith("_test.py"):
            fautives.append(regle)

    assert not fautives, (
        "règles non ancrées dans .gitignore : " + ", ".join(fautives) +
        " — elles s'appliquent à TOUS les niveaux et finiront par avaler un vrai "
        "module (déjà arrivé avec shared/test_mode.py). Préfixer par « / »."
    )
