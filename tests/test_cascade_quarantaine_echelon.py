# -*- coding: utf-8 -*-
"""Un échelon qui EXPIRE ne doit pas coûter sa borne à CHAQUE message.

Mesure du 2026-09-18 : `google/gemma-4-31b-it` (NVIDIA) a répondu 26 fois d'affilée en
1,3 à 5,1 s — puis a expiré 9 fois de suite pendant plus de 40 minutes, alors que
`nemotron`, même compte et même point d'entrée, répondait en 3,3 s dans la même minute.
Ce n'était ni le réseau, ni un démarrage à froid, ni notre quota : l'échelon était parti.

Cet échelon venait d'être mis en TÊTE des cascades d'Alfred et de Johnny. Sans
quarantaine, chaque message leur coûtait 15 s de silence (`_BORNE_TEXTE`) avant que
ministral ne réponde — une régression pire que le défaut qu'on venait de corriger.

⚠️ La quarantaine de CLÉ ne couvre pas ce cas, et c'est délibéré : elle ne se déclenche
que sur un 429 ([[gotcha-503-quarantaine-cle]]). Un dépassement de délai ne dit rien de
la clé — il parle du couple (fournisseur, modèle).
"""
import os
import sys
import time

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import shared.llm_cascade as cascade

BOTS = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]


def _vider_la_quarantaine():
    cascade._QUARANTAINE_ECHELON.clear()
    cascade._ECHECS_ECHELON.clear()


def test_un_echelon_sain_n_est_jamais_saute():
    _vider_la_quarantaine()
    assert cascade._echelon_en_quarantaine("nvidia", "google/gemma-4-31b-it") is False


def test_un_SEUL_depassement_ne_suffit_pas():
    """`gpt-oss-120b` met legitimement 7,75 s sur une question ouverte : un hoquet isole
    ne doit pas ecarter la tete de cascade de Sheogorath pendant cinq minutes."""
    _vider_la_quarantaine()
    assert cascade._ecarter_l_echelon("groq", "openai/gpt-oss-120b") is False
    assert cascade._echelon_en_quarantaine("groq", "openai/gpt-oss-120b") is False


def test_une_REPONSE_efface_l_ardoise():
    """Deux hoquets separes par des heures de bon fonctionnement ne s'additionnent pas."""
    _vider_la_quarantaine()
    cascade._ecarter_l_echelon("groq", "openai/gpt-oss-120b")
    cascade._echelon_a_repondu("groq", "openai/gpt-oss-120b")
    assert cascade._ecarter_l_echelon("groq", "openai/gpt-oss-120b") is False,         "le compteur n'a pas ete remis a zero par la reponse"


def test_deux_depassements_de_suite_ecartent_l_echelon_puis_il_revient():
    _vider_la_quarantaine()
    cascade._ecarter_l_echelon("nvidia", "google/gemma-4-31b-it")
    assert cascade._ecarter_l_echelon("nvidia", "google/gemma-4-31b-it") is True
    assert cascade._echelon_en_quarantaine("nvidia", "google/gemma-4-31b-it") is True

    # La mise à l'écart est bornée dans le temps : on avance l'horloge en rapprochant
    # l'échéance, plutôt que d'attendre cinq minutes.
    cascade._QUARANTAINE_ECHELON[("nvidia", "google/gemma-4-31b-it")] = time.time() - 1
    assert cascade._echelon_en_quarantaine("nvidia", "google/gemma-4-31b-it") is False
    assert ("nvidia", "google/gemma-4-31b-it") not in cascade._QUARANTAINE_ECHELON, \
        "l'entrée expirée doit être purgée, sinon le dictionnaire grossit sans fin"


def test_ecarter_un_MODELE_ne_ferme_pas_le_FOURNISSEUR():
    """C'est tout l'intérêt : nemotron répondait en 3,3 s pendant que gemma était parti."""
    _vider_la_quarantaine()
    cascade._ecarter_l_echelon("nvidia", "google/gemma-4-31b-it")
    cascade._ecarter_l_echelon("nvidia", "google/gemma-4-31b-it")
    assert cascade._echelon_en_quarantaine("nvidia", "google/gemma-4-31b-it") is True
    assert cascade._echelon_en_quarantaine("nvidia", "nvidia/nemotron-3.5-lightning-30b-a3b") is False
    assert cascade._echelon_en_quarantaine("groq", "google/gemma-4-31b-it") is False


def test_la_boucle_SAUTE_l_echelon_ecarte_avant_de_l_appeler():
    """Verrou de câblage : la quarantaine doit être consultée DANS la boucle, avant l'appel.

    Sans cela, les helpers existeraient sans rien protéger
    ([[gotcha-import-ajoute-mais-pas-cable]]).
    """
    import ast

    chemin = os.path.join(_parent_dir, "shared", "llm_cascade.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read(), filename=chemin)

    boucles = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.For)
        and isinstance(n.target, ast.Tuple)
        and [getattr(e, "id", None) for e in n.target.elts] == ["client_type", "model_name"]
    ]
    assert boucles, "la boucle de cascade a changé de forme : vérifier ce verrou"

    appels = [
        n for n in ast.walk(boucles[0])
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_echelon_en_quarantaine"
    ]
    assert appels, "la boucle ne consulte pas la quarantaine : l'échelon mort serait rappelé"


def test_un_depassement_de_delai_ECARTE_l_echelon():
    """L'autre moitié du câblage : sans elle, rien n'entre jamais en quarantaine."""
    import ast

    chemin = os.path.join(_parent_dir, "shared", "llm_cascade.py")
    source = open(chemin, encoding="utf-8").read()
    arbre = ast.parse(source, filename=chemin)

    appels = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_ecarter_l_echelon"
    ]
    assert appels, "rien n'appelle `_ecarter_l_echelon` : la quarantaine resterait vide"
    assert "asyncio.TimeoutError" in source, \
        "le dépassement de délai n'est plus reconnu : tout échec écarterait l'échelon"


def test_le_saut_est_TRACE_comme_un_saut_pas_comme_une_panne():
    """Le tableau de bord comptait déjà les échelons SAUTÉS comme des erreurs — 230 sur
    287. Un saut délibéré porte donc une `raison`, et jamais un code d'erreur."""
    chemin = os.path.join(_parent_dir, "shared", "llm_cascade.py")
    source = open(chemin, encoding="utf-8").read()
    assert 'quarantaine_echelon' in source


def test_les_6_copies_vendorisees_ont_la_quarantaine():
    """Un bot déployé seul doit être protégé aussi : `shared/` est VENDORÉ."""
    for bot in BOTS:
        chemin = os.path.join(_parent_dir, bot, "core", "llm_cascade.py")
        assert os.path.exists(chemin), f"{chemin} manquant"
        src = open(chemin, encoding="utf-8").read()
        for attendu in ("_QUARANTAINE_ECHELON", "def _echelon_en_quarantaine",
                        "def _ecarter_l_echelon", "def _echelon_a_repondu",
                        "quarantaine_echelon"):
            assert attendu in src, f"{bot} : {attendu} absent de la copie vendorisée"
