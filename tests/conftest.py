# -*- coding: utf-8 -*-
"""Garde globale : les tests ne doivent JAMAIS écrire dans logs/* (le dashboard
les afficherait comme des événements des bots live). Posé AVANT tout import de
module bot par les tests — conftest est chargé en premier par pytest."""
import os
import tempfile

os.environ.setdefault("BOTS_LOG_CONSOLE_ONLY", "1")

# Même garde pour data/. Depuis que la cascade trace ses appels, un test qui appelle
# `generate_response` (test_cascade_reponse_vide) écrivait de vraies lignes dans
# `data/api_usage.db` : la suite de l'hôte se mélangeait aux mesures des bots live,
# avec un bot_name « test ». Mesuré le 2026-08-29 : 40 lignes parasites.
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="pytest-data-"))

import glob
from pathlib import Path

_racine = Path(__file__).resolve().parent.parent
BOT_FILES = glob.glob(str(_racine / "*Bot" / "bot_*.py")) + [
    str(_racine / "Alfred" / "bot_alfred.py"),
    str(_racine / "Sheogorath" / "bot_sheogorath.py")
]


# La quarantaine d'echelon de la cascade est un etat de MODULE : voulu en production
# (chaque bot a le sien, il meurt au redemarrage), mais il fuit d'un test a l'autre.
# Vu le 2026-09-18 : un test qui fait expirer Groq ecartait l'echelon, et un test SUIVANT,
# dans un autre fichier, voyait sa tete de cascade sautee sans rien y comprendre.
import pytest


@pytest.fixture(autouse=True)
def _quarantaine_echelon_vierge():
    """Chaque test part d'une cascade sans echelon ecarte."""
    try:
        import shared.llm_cascade as _cascade
    except Exception:
        yield
        return
    _cascade._QUARANTAINE_ECHELON.clear()
    _cascade._ECHECS_ECHELON.clear()
    yield
    _cascade._QUARANTAINE_ECHELON.clear()
    _cascade._ECHECS_ECHELON.clear()
