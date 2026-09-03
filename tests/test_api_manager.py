"""Qui est puni quand un appel echoue : la cle, ou le modele ?

Le 2026-09-03, un `503 UNAVAILABLE` (« this model is currently experiencing high
demand ») mettait la CLE en quarantaine 120 s. Comme la cascade IMAGE enchaine deux
modeles Gemini sur la MEME cle, et que chaque bot n'a qu'une cle, un hoquet d'une seconde
chez Google rendait le bot aveugle deux minutes.

Un 503 ou un 500 parlent du MODELE ; un 400 ou un 408 parlent de la REQUETE. Seuls
401/403 (cle revoquee) et 429 (quota) parlent de la cle.
"""
import os
import time
from pathlib import Path

import pytest

from shared.api_manager import MultiAPIKeyManager
from shared.llm_cascade import delai_de_reprise

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


# --------------------------------------------------------------------------------------
# Duree de la quarantaine 429 : ecouter le fournisseur plutot que de deviner
# --------------------------------------------------------------------------------------
#
# Le 2026-09-03, `cooldown_times[429]` valait 3600 s — une valeur inventee. Un 429 peut
# dire « trop de requetes cette MINUTE » comme « quota du JOUR epuise » : une heure est
# trop long pour l'un, trop court pour l'autre. Google, lui, annonce le delai.


def _erreur_429_gemini(retry_delay="24s"):
    """Un vrai 429 du SDK google-genai, pas une imitation aplatie.

    ⚠️ `APIError.details` est le JSON COMPLET de la reponse : le RetryInfo est au
    troisieme niveau. Un test qui fabrique `details = [{...RetryInfo...}]` teste une forme
    qui n'existe pas, et laisse passer un extracteur qui ne descend jamais.
    """
    from google.genai.errors import ClientError

    details = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaMetric": "generate_requests_per_model_per_day"}]}]
    if retry_delay is not None:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": retry_delay})
    return ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                       "message": "You exceeded your current quota.",
                                       "details": details}})


def test_le_delai_est_lu_dans_un_vrai_429_du_sdk():
    assert delai_de_reprise(_erreur_429_gemini("24s")) == 24.0


def test_la_forme_aplatie_reste_acceptee():
    """Certains SDK rendent directement la liste des blocs RPC."""
    class _Exc(Exception):
        pass

    e = _Exc()
    e.details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"}]
    assert delai_de_reprise(e) == 7.0


@pytest.mark.parametrize("details", [
    None,                                   # pas de details du tout
    [],                                     # liste vide
    "chaine inattendue",                    # pas une structure
    {"error": {"code": 429}},               # un 429 sans RetryInfo
    {"error": {"details": "pas une liste"}},
    [{"@type": ".../RetryInfo", "retryDelay": "vingt"}],   # valeur illisible
    [{"@type": ".../RetryInfo", "retryDelay": True}],      # booleen : pas une duree
])
def test_l_extracteur_ne_leve_jamais(details):
    """Il tourne DEJA dans un `except` : lever le ferait disparaitre l'erreur d'origine."""
    class _Exc(Exception):
        pass

    e = _Exc()
    if details is not None:
        e.details = details
    assert delai_de_reprise(e) is None


def test_le_delai_annonce_gouverne_vraiment_la_quarantaine():
    """Le bout en bout : de l'exception du SDK jusqu'a la duree posee sur la cle."""
    mgr = _manager()
    t0 = time.time()
    mgr.report_error("gemini", "key1", 429,
                     retry_delay_s=delai_de_reprise(_erreur_429_gemini("24s")))
    attente = mgr.apis["gemini"]["status"]["key1"]["cooldown"] - t0
    assert 23 <= attente <= 25, f"quarantaine de {attente:.0f}s au lieu des 24s annoncees"


def test_sans_delai_annonce_on_attend_une_minute_pas_une_heure():
    mgr = _manager()
    t0 = time.time()
    mgr.report_error("gemini", "key1", 429,
                     retry_delay_s=delai_de_reprise(_erreur_429_gemini(retry_delay=None)))
    attente = mgr.apis["gemini"]["status"]["key1"]["cooldown"] - t0
    assert 59 <= attente <= 61, f"quarantaine de {attente:.0f}s : le repli n'est pas 60s"


@pytest.mark.parametrize("annonce, attendu", [
    (24, 24),        # nominal
    (0, 5),          # borne basse
    (-10, 5),
    (9999, 900),     # borne haute
    ("vingt", 60),   # illisible : repli
    (None, 60),      # rien d'annonce : repli
])
def test_les_bornes_de_la_quarantaine(annonce, attendu):
    mgr = _manager()
    t0 = time.time()
    mgr.report_error("gemini", "key1", 429, retry_delay_s=annonce)
    attente = mgr.apis["gemini"]["status"]["key1"]["cooldown"] - t0
    assert attendu - 1 <= attente <= attendu + 1, f"{annonce} -> {attente:.0f}s, attendu {attendu}s"


def test_3600_ne_figure_plus_dans_les_7_copies():
    """Le nombre lui-meme doit disparaitre : le laisser, c'est le voir revenir."""
    chemins = [RACINE / "shared" / "api_manager.py"]
    chemins += [RACINE / bot / "core" / "api_manager.py" for bot in BOTS]
    trouves = 0
    for chemin in chemins:
        source = chemin.read_text(encoding="utf-8")
        trouves += 1
        assert "3600" not in source, f"{chemin} garde encore la quarantaine d'une heure."
    # ⚠️ Deriver le compte de la liste de depart, pas de la boucle.
    assert trouves == 7, f"Toutes les copies n'ont pas ete inspectees : {trouves}/7"
