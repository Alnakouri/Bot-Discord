# -*- coding: utf-8 -*-
"""/quests et /stats retirees des six bots (2026-10-01, decision d'Ahmed).

Elles tournaient a VIDE depuis l'origine, constate en lecture seule le 01/10 :
- /stats lisait `bot_interactions` : 0 ligne en base, et `log_bot_interaction` n'a jamais
  eu un seul appelant (`git log -S` : rien depuis l'Initial commit). Reponse eternelle :
  « Aucun duel enregistre ».
- /quests distribuait des quetes que rien ne pouvait valider (`complete_quest` sans
  appelant) et qui citaient des features retirees (rumeurs de M'aiq, mini-jeux).

Une commande qui repond toujours vide a l'air d'une panne pour qui la tape.
"""
import ast
from pathlib import Path

import pytest

from shared.slash_commands import setup_slash_commands, _AIDE

from .test_alfred_allege import _FauxBot

RACINE = Path(__file__).resolve().parent.parent
MODULE = RACINE / "shared" / "slash_commands.py"
RETIREES = {"quests", "stats"}


def test_aucun_bot_ne_pose_quests_ni_stats():
    bot = _FauxBot()
    setup_slash_commands(bot, "Test")
    assert not RETIREES & set(bot.tree.poses)


def test_help_ne_les_promet_plus():
    assert not RETIREES & {nom for nom, _, _ in _AIDE}


@pytest.mark.parametrize("nom", sorted(RETIREES))
def test_les_retirer_par_sans_est_une_faute(nom):
    # Un bot qui garderait `sans={"quests"}` planterait au demarrage : on le refuse ici.
    with pytest.raises(ValueError):
        setup_slash_commands(_FauxBot(), "Test", sans={nom})


def test_le_module_n_importe_plus_leurs_fonctions():
    arbre = ast.parse(MODULE.read_text(encoding="utf-8"))
    importes = {
        alias.name
        for node in ast.walk(arbre)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    for nom in ("complete_quest", "create_daily_quests", "get_bot_interaction_stats"):
        assert nom not in importes, f"{nom} encore importe : la commande est-elle revenue ?"


def test_aucun_bot_ne_passe_un_nom_retire_dans_sans():
    from .conftest import BOT_FILES
    assert len(BOT_FILES) == 6
    for fichier in BOT_FILES:
        arbre = ast.parse(Path(fichier).read_text(encoding="utf-8"))
        for node in ast.walk(arbre):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setup_slash_commands":
                for kw in node.keywords:
                    if kw.arg == "sans":
                        noms = {c.value for c in ast.walk(kw.value) if isinstance(c, ast.Constant)}
                        assert not RETIREES & noms, f"{Path(fichier).name} : sans={noms}"
