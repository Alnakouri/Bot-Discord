"""Qui met une clé en quarantaine, et qui reste dehors ?

Jusqu'au 2026-09-06, `report_error` n'était appelé QUE pour Gemini. Groq, Mistral et
NVIDIA prenaient donc un 429 sans jamais écarter leur clé : au message suivant, la
cascade retapait dans le même mur. Mesuré dans `data/api_usage.db` :

    2026-09-04 05:30:45  johnny  mistral  429   (x3, dans la MEME seconde)
    2026-09-04 05:30:59  sheo    mistral  429   (x2)
    2026-09-06 13:28:45  sheo    groq     429

Et NVIDIA n'était même pas enregistré auprès du gestionnaire de clés : sans pool, sa clé
ne POUVAIT pas être écartée, et son index restait absent de `api_key_status`.

⚠️ Le piège que ces tests gardent ouvert : une clé introuvable ne doit JAMAIS faire
sauter un échelon facultatif. Le client est déjà bâti et porte sa propre clé ; un
`register_api` oublié rendrait sinon le fournisseur définitivement muet, sans une ligne
de journal — exactement ce qui a laissé NVIDIA annoncé sur les 6 bots et sans un seul
appel pendant huit jours.
"""
import ast
import time
from pathlib import Path

import pytest

from shared.api_manager import MultiAPIKeyManager
from shared.llm_cascade import (
    _cle_du_pool,
    _delai_dans_les_entetes,
    _duree_en_secondes,
    delai_de_reprise,
)

RACINE = Path(__file__).resolve().parent.parent
BOTS = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]
FOURNISSEURS = ["gemini", "mistral", "groq", "nvidia"]

# Les 4 bots qui ont RECOPIE la cascade au lieu de l'appeler. Corriger `shared/` seul ne
# les couvre pas : c'est la leçon de chaque lot depuis le 2026-08-25.
CASCADES_INLINE = {
    "Alfred": "Alfred/bot_alfred.py",
    "MaiqBot": "MaiqBot/bot_maiq.py",
    "MalenaBot": "MalenaBot/bot_malena.py",
    "Sheogorath": "Sheogorath/bot_sheogorath.py",
}


# --------------------------------------------------------------------------------------
# Le délai annoncé : Gemini le met dans le CORPS, les autres dans une EN-TETE
# --------------------------------------------------------------------------------------

class _Entetes:
    def __init__(self, **kw):
        self._d = {k.replace("_", "-"): v for k, v in kw.items()}

    def get(self, nom):
        return self._d.get(nom)


class _Reponse:
    def __init__(self, **kw):
        self.headers = _Entetes(**kw)


def _erreur_429_entetes(**kw):
    """Un 429 de SDK style OpenAI : le délai est dans la réponse, pas dans `details`."""
    e = Exception("Rate limit reached")
    e.response = _Reponse(**kw)
    e.status_code = 429
    return e


@pytest.mark.parametrize("brut, attendu", [
    ("24", 24.0),                 # `retry-after` nu : des secondes
    ("7.66s", 7.66),              # Groq, remise à zéro des tokens
    ("2m59.56s", 179.56),         # au-delà de la minute, Groq compose les unités
    ("500ms", 0.5),
    ("1h", 3600.0),
    ("0", 0.0),
])
def test_les_durees_des_en_tetes_sont_lues(brut, attendu):
    assert _duree_en_secondes(brut) == pytest.approx(attendu)


@pytest.mark.parametrize("brut", [
    "Wed, 21 Oct 2015 07:28:00 GMT",  # `retry-after` peut être une DATE : refus délibéré
    "bientot",
    "",
    "12 secondes",
])
def test_une_duree_illisible_rend_none_plutot_qu_un_nombre_absurde(brut):
    assert _duree_en_secondes(brut) is None


def test_le_delai_groq_est_lu_dans_l_en_tete():
    assert _delai_dans_les_entetes(_erreur_429_entetes(retry_after="24")) == 24.0


def test_delai_de_reprise_couvre_les_deux_formes():
    """⚠️ L'extracteur ne lisait que la forme Google : sur Groq il rendait toujours None,
    donc toute quarantaine serait retombée sur ses 60 s par défaut."""
    assert delai_de_reprise(_erreur_429_entetes(retry_after="8.5")) == 8.5


def test_l_extracteur_d_en_tetes_ne_leve_jamais():
    """Il tourne DEJA dans un `except` : lever ferait disparaître l'erreur d'origine."""
    class _Cassee(Exception):
        @property
        def response(self):
            raise RuntimeError("SDK capricieux")

    assert delai_de_reprise(_Cassee()) is None
    assert delai_de_reprise(object()) is None


def test_le_delai_groq_gouverne_vraiment_la_quarantaine():
    """Le bout en bout : de l'exception du SDK jusqu'à la durée posée sur la clé."""
    mgr = MultiAPIKeyManager()
    mgr.register_api("groq", ["gsk_1"])
    t0 = time.time()
    erreur = _erreur_429_entetes(retry_after="24")
    mgr.report_error("groq", "gsk_1", 429, retry_delay_s=delai_de_reprise(erreur))
    attente = mgr.apis["groq"]["status"]["gsk_1"]["cooldown"] - t0
    assert 23 <= attente <= 25, f"quarantaine de {attente:.0f}s au lieu des 24s annoncées"
    assert mgr.is_api_available("groq") is False


# --------------------------------------------------------------------------------------
# `_cle_du_pool` : quand sauter un échelon, et surtout quand NE PAS le sauter
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("api", FOURNISSEURS)
def test_une_cle_saine_est_rendue_sans_saut(api):
    mgr = MultiAPIKeyManager()
    mgr.register_api(api, ["k1"])
    cle, saut = _cle_du_pool(mgr, api)
    assert (cle, saut) == ("k1", None)


@pytest.mark.parametrize("api", FOURNISSEURS)
def test_une_cle_en_quarantaine_fait_sauter_l_echelon(api):
    mgr = MultiAPIKeyManager()
    mgr.register_api(api, ["k1"])
    mgr.report_error(api, "k1", 429, retry_delay_s=30)
    cle, saut = _cle_du_pool(mgr, api)
    assert cle is None
    assert saut == "quarantaine", (
        "Le saut doit se nommer : `tracer_appel` le range en base sous cette raison, "
        "et un saut anonyme redevient un échelon invisible."
    )


@pytest.mark.parametrize("api", ["mistral", "groq", "nvidia"])
def test_un_pool_non_enregistre_ne_fait_PAS_sauter_un_echelon_facultatif(api):
    """⚠️ La garde la plus importante du lot.

    Le client est bâti au démarrage et porte déjà sa clé : le pool ne sert qu'à la
    quarantaine. Sauter l'échelon parce que le pool manque rendrait le fournisseur muet
    sur un simple `register_api` oublié — sans erreur, sans journal, comme NVIDIA huit
    jours durant.
    """
    mgr = MultiAPIKeyManager()          # aucun pool enregistré
    cle, saut = _cle_du_pool(mgr, api)
    assert saut is None, f"un pool {api} absent ne doit jamais faire sauter l'échelon"
    assert cle is None


def test_gemini_lui_ne_peut_pas_tourner_sans_sa_cle():
    """Gemini bâtit son client AVEC la clé : sans elle, l'échelon est impossible."""
    mgr = MultiAPIKeyManager()
    cle, saut = _cle_du_pool(mgr, "gemini", exigee=True)
    assert (cle, saut) == (None, "pas_de_cle")


def test_un_gestionnaire_sans_pools_ne_fait_pas_lever():
    """Certains outils passent un faux gestionnaire minimal (cf. tools/sonde_nvidia.py)."""
    class _Faux:
        def get_key(self, _nom):
            return None

    assert _cle_du_pool(_Faux(), "groq") == (None, None)


# --------------------------------------------------------------------------------------
# Le câblage : 11 cascades, et il faut les onze
# --------------------------------------------------------------------------------------

def _fonctions_de_cascade(source, chemin):
    """Les fonctions qui portent une boucle `for client_type, model_name in cascade`.

    ⚠️ Chercher le NOM d'un helper dans le fichier ne prouve rien : un simple import
    suffirait à faire passer le test. On exige l'APPEL, avec ses arguments, à l'endroit
    exact où la cascade tourne.
    """
    arbre = ast.parse(source, filename=str(chemin))
    trouvees = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for interne in ast.walk(noeud):
            if (isinstance(interne, ast.For)
                    and isinstance(interne.target, ast.Tuple)
                    and [getattr(el, "id", None) for el in interne.target.elts]
                        == ["client_type", "model_name"]):
                trouvees.append(noeud)
                break
    return trouvees


def _pools_demandes(fonction):
    """Les fournisseurs pour lesquels la cascade demande sa clé au gestionnaire."""
    pools = set()
    for noeud in ast.walk(fonction):
        if (isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Name)
                and noeud.func.id == "_cle_du_pool"
                and len(noeud.args) >= 2
                and isinstance(noeud.args[1], ast.Constant)):
            pools.add(noeud.args[1].value)
    return pools


def _premiers_arguments_de_report_error(fonction):
    """Le 1er argument de chaque `report_error` : une constante "gemini", ou client_type ?"""
    args = []
    for noeud in ast.walk(fonction):
        if (isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Attribute)
                and noeud.func.attr == "report_error"
                and noeud.args):
            premier = noeud.args[0]
            args.append(premier.id if isinstance(premier, ast.Name)
                        else getattr(premier, "value", "?"))
    return args


def _toutes_les_cascades():
    chemins = [RACINE / "shared" / "llm_cascade.py"]
    chemins += [RACINE / bot / "core" / "llm_cascade.py" for bot in BOTS]
    chemins += [RACINE / rel for rel in CASCADES_INLINE.values()]
    return chemins


def test_les_11_cascades_sont_bien_toutes_la():
    """7 copies du noyau + 4 recopiées à la main dans les bots."""
    chemins = _toutes_les_cascades()
    assert len(chemins) == 11
    manquants = [str(c) for c in chemins if not c.exists()]
    assert not manquants, f"cascade introuvable : {manquants}"


@pytest.mark.parametrize("chemin", _toutes_les_cascades(),
                         ids=lambda c: f"{c.parent.name}/{c.name}")
def test_chaque_cascade_demande_sa_cle_pour_les_4_fournisseurs(chemin):
    source = chemin.read_text(encoding="utf-8")
    fonctions = _fonctions_de_cascade(source, chemin)
    assert fonctions, f"{chemin} : aucune boucle de cascade trouvée"
    for fonction in fonctions:
        pools = _pools_demandes(fonction)
        manquants = set(FOURNISSEURS) - pools
        assert not manquants, (
            f"{chemin}::{fonction.name} ne demande pas sa clé pour {sorted(manquants)} : "
            "ces échelons ne peuvent donc ni être sautés en quarantaine, ni voir leur "
            "clé écartée sur un 429."
        )


@pytest.mark.parametrize("chemin", _toutes_les_cascades(),
                         ids=lambda c: f"{c.parent.name}/{c.name}")
def test_aucune_cascade_ne_signale_plus_gemini_en_dur(chemin):
    source = chemin.read_text(encoding="utf-8")
    for fonction in _fonctions_de_cascade(source, chemin):
        premiers = _premiers_arguments_de_report_error(fonction)
        assert premiers, f"{chemin}::{fonction.name} : plus aucun report_error"
        assert all(a == "client_type" for a in premiers), (
            f"{chemin}::{fonction.name} signale encore {premiers} en dur : les autres "
            "fournisseurs ne mettent alors jamais leur clé en quarantaine."
        )


@pytest.mark.parametrize("bot", BOTS)
def test_les_6_bots_enregistrent_le_pool_nvidia(bot):
    """⚠️ « fait sur les 6 » l'est presque toujours sur 5 : on compte les six."""
    fichiers = list((RACINE / bot).glob("bot_*.py"))
    assert len(fichiers) == 1, f"{bot} : {len(fichiers)} fichier(s) bot_*.py"
    source = fichiers[0].read_text(encoding="utf-8")
    arbre = ast.parse(source, filename=str(fichiers[0]))
    enregistres = set()
    for noeud in ast.walk(arbre):
        if (isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Attribute)
                and noeud.func.attr == "register_api"
                and noeud.args
                and isinstance(noeud.args[0], ast.Constant)):
            enregistres.add(noeud.args[0].value)
    manquants = set(FOURNISSEURS) - enregistres
    assert not manquants, (
        f"{bot} n'enregistre pas {sorted(manquants)} : sans pool, la clé de ce "
        "fournisseur ne peut pas être mise en quarantaine sur un 429."
    )


# --------------------------------------------------------------------------------------
# La preuve de bout en bout : le 2e message ne retape pas dans le mur
# --------------------------------------------------------------------------------------
#
# ⚠️ `asyncio.run`, pas `@pytest.mark.asyncio` : `pytest-asyncio` n'est PAS installé ici
# (pytest le dit lui-même, « Unknown config option: asyncio_mode »). Un test async
# marqué serait collecté, jamais exécuté, et vert — un verrou qui s'auto-désarme.

class _FauxMessage:
    def __init__(self, contenu):
        self.content = contenu
        self.reasoning = None


class _FauxChoix:
    def __init__(self, contenu):
        self.message = _FauxMessage(contenu)


class _FauxChat:
    def __init__(self, contenu):
        self.choices = [_FauxChoix(contenu)]


class _FauxGroq429:
    """Un client Groq qui rend un 429 avec son en-tête, et qui COMPTE ses appels."""

    def __init__(self):
        self.appels = 0
        self.chat = self
        self.completions = self

    def create(self, **_kw):
        self.appels += 1
        raise _erreur_429_entetes(retry_after="45")


class _FauxNvidia:
    """L'échelon suivant : il répond, pour que la cascade ait une issue."""

    def __init__(self):
        self.appels = 0
        self.chat = self
        self.completions = self

    def create(self, **_kw):
        self.appels += 1
        return _FauxChat("Bonsoir.")


def _un_message(mgr, groq, nvidia):
    import asyncio

    import shared.llm_cascade as cascade
    from shared.smart_router import RequestType

    return asyncio.run(cascade.generate_response(
        routing={"type": RequestType.TEXT, "reason": "test"},
        system_prompt="sys", transcript="", user_message="coucou",
        conversation_history=[], media_data=None, mime_type="",
        key_manager=mgr, mistral_client=None,
        groq_client=groq, nvidia_client=nvidia, bot_label="Test",
        cascade=[("groq", "modele-groq"), ("nvidia", "modele-nvidia")],
    ))


def test_apres_un_429_groq_le_message_suivant_saute_l_echelon():
    """⚠️ C'est le comportement que tout ce lot existe pour obtenir.

    Avant, chaque message rejouait l'échelon mort : trois appels Mistral de Johnny sur la
    même clé dans la même seconde (2026-09-04 05:30:45). Ici, le 2e message ne doit plus
    toucher Groq du tout — et il doit quand même obtenir une réponse.
    """
    mgr = MultiAPIKeyManager()
    mgr.register_api("groq", ["gsk_1"])
    mgr.register_api("nvidia", ["nv_1"])
    groq, nvidia = _FauxGroq429(), _FauxNvidia()

    assert _un_message(mgr, groq, nvidia) == "Bonsoir."
    assert groq.appels == 1
    assert mgr.is_api_available("groq") is False, "le 429 n'a pas écarté la clé Groq"

    assert _un_message(mgr, groq, nvidia) == "Bonsoir."
    assert groq.appels == 1, (
        "Groq a été rappelé alors que sa clé était en quarantaine : l'échelon n'est pas "
        "sauté, et on retape dans le mur à chaque message."
    )
    assert nvidia.appels == 2, "l'échelon de secours doit, lui, servir les deux fois"


def test_la_quarantaine_d_un_fournisseur_n_atteint_pas_les_autres():
    """Écarter Groq ne doit pas rendre NVIDIA muet : les pools sont indépendants."""
    mgr = MultiAPIKeyManager()
    mgr.register_api("groq", ["gsk_1"])
    mgr.register_api("nvidia", ["nv_1"])
    mgr.report_error("groq", "gsk_1", 429, retry_delay_s=60)
    groq, nvidia = _FauxGroq429(), _FauxNvidia()

    assert _un_message(mgr, groq, nvidia) == "Bonsoir."
    assert groq.appels == 0
    assert nvidia.appels == 1


def test_sans_gestionnaire_de_cles_la_cascade_tourne_quand_meme():
    """⚠️ Plusieurs appelants passent `key_manager=None` (cf. test_cascade_reponse_vide).

    La quarantaine ne doit jamais devenir une condition d'existence de la cascade.
    """
    groq, nvidia = _FauxGroq429(), _FauxNvidia()
    assert _un_message(None, groq, nvidia) == "Bonsoir."
    assert groq.appels == 1, "sans gestionnaire, Groq doit être tenté normalement"


def test_un_gestionnaire_dont_seul_get_key_est_remplace_rend_bien_sa_cle():
    """⚠️ Le test que le local ne pouvait pas faire échouer — et la CI, si.

    Trois tests du dépôt (`test_sheo_images`, `test_timeout_media`) ne remplacent que
    `key_manager.get_key`, sans peupler `apis`. Une première version de `_cle_du_pool`
    interrogeait `apis` AVANT `get_key` : en local elle passait, parce que les vraies
    clés Gemini y sont ; en CI, sans clé, la branche Gemini n'était plus jamais atteinte
    et les trois tests tombaient.

    La règle qui en sort : le gestionnaire est la seule autorité sur « ai-je une clé ».
    On la lui demande, et on n'interprète que son refus.
    """
    class _SeulementGetKey:
        def get_key(self, _nom):
            return "FAKE_KEY"

    assert _cle_du_pool(_SeulementGetKey(), "gemini", exigee=True) == ("FAKE_KEY", None)
    assert _cle_du_pool(_SeulementGetKey(), "groq") == ("FAKE_KEY", None)


def test_un_faux_gestionnaire_ne_rend_pas_une_fausse_cle():
    """⚠️ Une clé est une chaîne, ou n'est pas.

    Plusieurs tests du dépôt passent un `MagicMock` en guise de gestionnaire. Son
    `get_key` rend un MagicMock — qui n'est pas `None`. Cette fausse clé descendait
    jusqu'à `tracer_appel`, où SQLite la refusait :
    « Error binding parameter 5: type 'MagicMock' is not supported ». L'appel n'était
    alors plus tracé du tout, et le chantier du suivi API perdait ses lignes.
    """
    from unittest.mock import MagicMock

    assert _cle_du_pool(MagicMock(), "groq") == (None, None)
    assert _cle_du_pool(MagicMock(), "gemini", exigee=True) == (None, "pas_de_cle")

    class _CleVide:
        def get_key(self, _nom):
            return ""

    assert _cle_du_pool(_CleVide(), "groq") == (None, None)


# --------------------------------------------------------------------------------------
# Une alerte qui crie pour du nominal est une alerte qu'on apprend à ignorer
# --------------------------------------------------------------------------------------
#
# `dashboard/backend/error_analyzer.py` classe « TOUTES LES CLÉS », « ZÉRO clé saine » et
# « CLÉS SONT ÉPUISÉES » en CRITICAL / « API Indisponible ». Depuis que la cascade demande
# sa clé pour les 4 fournisseurs, un quota Groq par minute — 8 000 tokens, dont le prompt
# de Sheo mange 56 % — passerait par là plusieurs fois par message.

MOTIFS_CRITIQUES_DU_DASHBOARD = ["TOUTES LES CLÉS", "ZÉRO clé saine", "CLÉS SONT ÉPUISÉES"]


def test_un_cooldown_passager_ne_declenche_pas_l_alerte_critique(caplog):
    """Un 429 avec un délai annoncé : la cascade bascule, ce n'est pas une panne."""
    mgr = MultiAPIKeyManager()
    mgr.register_api("groq", ["gsk_1"])
    with caplog.at_level("DEBUG"):
        mgr.report_error("groq", "gsk_1", 429, retry_delay_s=37)
        assert mgr.get_key("groq") is None
    journal = caplog.text
    coupables = [m for m in MOTIFS_CRITIQUES_DU_DASHBOARD if m in journal]
    assert not coupables, (
        f"un simple cooldown déclenche l'alerte CRITICAL du dashboard via {coupables} : "
        "le tableau de bord criera à la panne à chaque quota par minute."
    )
    assert "cooldown" in journal, "le cooldown doit quand même se voir dans le journal"


@pytest.mark.parametrize("code", [401, 403])
def test_une_cle_revoquee_declenche_bien_l_alerte_critique(code, caplog):
    """⚠️ L'inverse compte autant : aucun cooldown ne réparera une clé révoquée."""
    mgr = MultiAPIKeyManager()
    mgr.register_api("gemini", ["k1"])
    with caplog.at_level("DEBUG"):
        mgr.report_error("gemini", "k1", code)
        assert mgr.get_key("gemini") is None
    assert any(m in caplog.text for m in MOTIFS_CRITIQUES_DU_DASHBOARD), (
        "une clé révoquée doit rester visible comme une vraie panne dans le dashboard."
    )
