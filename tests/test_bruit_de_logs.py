# -*- coding: utf-8 -*-
"""Le bruit dans les logs n'est pas cosmetique : le dashboard compte les lignes ERROR.

Un compteur qui monte tout seul apprend a ignorer les erreurs, et le jour ou une vraie
tombe, personne ne la voit. Mesure du 2026-08-31 : un seul « !decret » produisait cinq
ERROR `CommandNotFound` (les 5 autres bots partagent le prefixe « ! ») et six lignes de
debug d'enigme.

Les tests lisent l'ARBRE SYNTAXIQUE plutot que le texte : une reformulation, un
renommage ou un reformatage ne doivent pas casser le verrou, mais retirer le
comportement, si.
"""
import ast
import pytest
from pathlib import Path

_RACINE = Path(__file__).resolve().parent.parent

BOTS = {
    "Alfred": "bot_alfred.py",
    "JohnnyBot": "bot_johnny.py",
    "MaiqBot": "bot_maiq.py",
    "MalenaBot": "bot_malena.py",
    "Sheogorath": "bot_sheogorath.py",
    "SugarBot": "bot_sugar.py",
}


def _fonction(chemin, nom):
    arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)) and noeud.name == nom:
            return noeud
    return None


@pytest.mark.parametrize("bot,fichier", sorted(BOTS.items()))
def test_chaque_bot_tait_les_commandes_qui_ne_sont_pas_les_siennes(bot, fichier):
    handler = _fonction(_RACINE / bot / fichier, "on_command_error")
    assert handler is not None, f"{bot} : pas de gestionnaire, discord.py logge en ERROR"

    # Un `isinstance(..., CommandNotFound)` qui mene a un `return` nu.
    silences = [
        n for n in ast.walk(handler)
        if isinstance(n, ast.If)
        and "CommandNotFound" in ast.dump(n.test)
        and any(isinstance(c, ast.Return) and c.value is None for c in n.body)
    ]
    assert silences, f"{bot} : CommandNotFound n'est pas tue explicitement"


@pytest.mark.parametrize("bot,fichier", sorted(BOTS.items()))
def test_le_gestionnaire_ne_rend_pas_muettes_les_vraies_erreurs(bot, fichier):
    """⚠️ Definir `on_command_error` REMPLACE celui de discord.py. Un handler qui se
    contenterait de `return` avalerait toutes les erreurs de commande — permissions
    manquantes, argument invalide, exception dans le corps — et on aurait echange du
    bruit contre du silence, ce qui est pire."""
    handler = _fonction(_RACINE / bot / fichier, "on_command_error")

    journalise = [
        n for n in ast.walk(handler)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in ("error", "exception", "warning")
    ]
    assert journalise, f"{bot} : aucune erreur n'est journalisee, tout devient muet"

    # Et le `return` nu doit etre SOUS la condition, jamais au premier niveau du corps.
    assert not any(isinstance(n, ast.Return) and n.value is None for n in handler.body), \
        f"{bot} : un return inconditionnel avale toutes les erreurs"


# MaiqBot/minigames.py (les enigmes) a ete supprime par la SUITE 17 : seul reste celui
# de Sheogorath (le fromage).
@pytest.mark.parametrize("bot", ["Sheogorath"])
def test_l_enigme_ne_parle_plus_par_print(bot):
    """`print` echappe au systeme de logs : aucun niveau ne peut le filtrer, et il
    sort a chaque message tant qu'une partie est ouverte — y compris sur les commandes
    des autres bots."""
    source = (_RACINE / bot / "minigames.py").read_text(encoding="utf-8")
    assert "DEBUG RIDDLE" not in source
    assert "logger.debug" in source, "la trace doit rester, mais filtrable"
