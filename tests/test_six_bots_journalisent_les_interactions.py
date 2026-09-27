# -*- coding: utf-8 -*-
"""Verrou : chacun des six bots journalise ses interactions dans la base partagée.

SUITE 11 (2026-09-27) : Alfred et Sheogorath n'écrivaient jamais dans `interactions`
alors que Sheogorath est le plus actif, ce qui faussait le graphe d'activité du dashboard.
Ce test vérifie par l'AST que les 6 bots appellent bien `log_interaction`.
"""
import ast
from pathlib import Path
import pytest

RACINE = Path(__file__).resolve().parent.parent

# ⚠️ Liste EN DUR des 6 bots (pas de glob pour éviter qu'un bot omis passe le test)
BOTS_FICHIERS = [
    "Alfred/bot_alfred.py",
    "Sheogorath/bot_sheogorath.py",
    "MaiqBot/bot_maiq.py",
    "JohnnyBot/bot_johnny.py",
    "SugarBot/bot_sugar.py",
    "MalenaBot/bot_malena.py",
]


def _a_appel_log_interaction(chemin: Path) -> bool:
    arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            if isinstance(noeud.func, ast.Name) and noeud.func.id == "log_interaction":
                return True
    return False


@pytest.mark.parametrize("rel_path", BOTS_FICHIERS)
def test_bot_journalise_interactions(rel_path):
    chemin = RACINE / rel_path
    assert chemin.is_file(), f"Fichier de bot introuvable : {rel_path}"
    assert _a_appel_log_interaction(chemin), (
        f"Le bot {rel_path} n'appelle pas `log_interaction` ! "
        f"Il doit enregistrer ses interactions dans la table partagée pour le dashboard."
    )
