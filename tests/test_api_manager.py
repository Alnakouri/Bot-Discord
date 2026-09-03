"""Qui est puni quand un appel echoue : la cle, ou le modele ?

Le 2026-09-03, un `503 UNAVAILABLE` (« this model is currently experiencing high
demand ») mettait la CLE en quarantaine 120 s. Comme la cascade IMAGE enchaine deux
modeles Gemini sur la MEME cle, et que chaque bot n'a qu'une cle, un hoquet d'une seconde
chez Google rendait le bot aveugle deux minutes.

Un 503 ou un 500 parlent du MODELE ; un 400 ou un 408 parlent de la REQUETE. Seuls
401/403 (cle revoquee) et 429 (quota) parlent de la cle.
"""
import os
from pathlib import Path

import pytest

from shared.api_manager import MultiAPIKeyManager

RACINE = Path(__file__).resolve().parent.parent
BOTS = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]

# Codes qui ne disent RIEN sur la sante de la cle.
CODES_MODELE_OU_REQUETE = [503, 500, 408, 529, 400]


def _manager():
    mgr = MultiAPIKeyManager()
    mgr.register_api("gemini", ["key1"])
    assert mgr.is_api_available("gemini") is True
    return mgr


@pytest.mark.parametrize("code", CODES_MODELE_OU_REQUETE)
def test_une_erreur_de_modele_ne_touche_pas_a_la_cle(code):
    mgr = _manager()
    mgr.report_error("gemini", "key1", code)
    assert mgr.is_api_available("gemini") is True, (
        f"Erreur {code} : elle parle du modele ou de la requete, pas de la cle. "
        "La mettre en quarantaine prive le bot de l'echelon suivant, qui utilise la "
        "MEME cle."
    )


def test_un_429_ecarte_bien_la_cle():
    mgr = _manager()
    mgr.report_error("gemini", "key1", 429)
    assert mgr.is_api_available("gemini") is False, (
        "Un 429 est un quota : la cle DOIT etre ecartee, sinon on tape dans le mur en "
        "boucle."
    )


@pytest.mark.parametrize("code", [401, 403])
def test_une_cle_revoquee_est_desactivee_pour_de_bon(code):
    mgr = _manager()
    mgr.report_error("gemini", "key1", code)
    assert mgr.is_api_available("gemini") is False


def test_les_7_copies_du_gestionnaire_portent_la_meme_regle():
    """⚠️ 7 copies (shared + 6 vendorisees) : corriger `shared/` seul ne suffit jamais."""
    chemins = [RACINE / "shared" / "api_manager.py"] + [
        RACINE / bot / "core" / "api_manager.py" for bot in BOTS
    ]
    trouves = 0
    for chemin in chemins:
        assert chemin.exists(), f"Copie manquante : {chemin}"
        trouves += 1
        source = chemin.read_text(encoding="utf-8")
        assert "if error_code == 429:" in source, (
            f"{chemin} ne distingue pas le 429 des erreurs de modele : une erreur 503 y "
            "condamne encore la cle."
        )
    # ⚠️ Deriver le compte de la liste de depart, pas de la boucle.
    assert trouves == 7, f"Toutes les copies n'ont pas ete inspectees : {trouves}/7"
