# -*- coding: utf-8 -*-
"""Vérifie que les réactions emoji de Sheogorath respectent les contraintes :
1. Mots entiers uniquement (sans faux positifs sur sous-chaînes) ;
2. Déduplication des emojis (ex: 'fromages' et 'brie' -> un seul 🧀) ;
3. Positionnées STRICTEMENT APRÈS la garde author.bot dans on_message.
"""
import ast
import re
from pathlib import Path
import pytest

RACINE = Path(__file__).resolve().parent.parent
CHEMIN = RACINE / "Sheogorath" / "bot_sheogorath.py"
SOURCE = CHEMIN.read_text(encoding="utf-8")
ARBRE = ast.parse(SOURCE, filename=str(CHEMIN))


def _charger():
    """Exécute REACTIONS_MOTS, _MOTIFS_REACTIONS et _emojis_des_mots DU FICHIER DU BOT."""
    noeuds = [n for n in ARBRE.body
              if (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in
                  ("REACTIONS_MOTS", "_MOTIFS_REACTIONS") for t in n.targets))
              or (isinstance(n, ast.FunctionDef) and n.name == "_emojis_des_mots")]
    assert len(noeuds) == 3, "table, motifs ou fonction introuvables au niveau du module"
    espace = {"re": re}
    exec(compile(ast.Module(body=noeuds, type_ignores=[]), str(CHEMIN), "exec"), espace)
    return espace["_emojis_des_mots"]


@pytest.mark.parametrize(
    "texte,attendu",
    [
        ("J'adore le fromage", ["🧀"]),
        ("Des fromages et du brie", ["🧀"]),
        ("Gabriel est là", []),
        ("Quel désordre", []),
        ("L'ORDRE de Jyggalag", ["⚖️"]),
        ("Wesh le sang", ["🩸"]),
        ("sanglier", []),
        ("La démence !", ["🧠"]),
        ("", []),
        (None, []),
    ],
)
def test_emojis_des_mots(texte, attendu):
    emojis_fn = _charger()
    assert emojis_fn(texte) == attendu


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
