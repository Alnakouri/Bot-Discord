# -*- coding: utf-8 -*-
"""Un modèle peut répondre 200 OK avec un contenu VIDE, sans lever d'exception.

Vu en prod le 2026-08-26 : Groq (openai/gpt-oss-120b) rend un contenu vide, le bot
tente alors un envoi Discord vide -> 400 « Cannot send an empty message », et l'user
voit « (Erreur API) ». Le vide n'est pas une réponse : la cascade doit descendre d'un
échelon au lieu de s'arrêter là.

Ce test verrouille les DEUX implémentations : la cascade partagée (shared + les 6
copies vendorisées) et la cascade INLINE de Malena, qui ne passe pas par elle.
"""
import asyncio
import os
import sys

import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.llm_cascade import _est_vide as _est_vide_partage
from shared.smart_router import RequestType


VIDES = [None, "", "   ", "\n", "\t\n  "]
NON_VIDES = ["a", " oui ", "0", "🔥"]


@pytest.mark.parametrize("valeur", VIDES)
def test_est_vide_detecte_le_vide(valeur):
    assert _est_vide_partage(valeur) is True


@pytest.mark.parametrize("valeur", NON_VIDES)
def test_est_vide_laisse_passer_le_contenu(valeur):
    assert _est_vide_partage(valeur) is False


def test_les_6_copies_vendorisees_ont_le_garde_fou():
    """Le garde-fou doit exister dans chaque <Bot>/core/llm_cascade.py, pas seulement
    dans shared/ — sinon un bot déployé seul reste exposé."""
    bots = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]
    for bot in bots:
        chemin = os.path.join(_parent_dir, bot, "core", "llm_cascade.py")
        assert os.path.exists(chemin), f"{chemin} manquant"
        src = open(chemin, encoding="utf-8").read()
        assert "def _est_vide" in src, f"{bot} : helper _est_vide absent"
        for fournisseur in ("GEMINI", "MISTRAL", "GROQ", "NVIDIA"):
            assert f"[{fournisseur} {{model_name}}] réponse vide" in src, \
                f"{bot} : branche {fournisseur} sans garde-fou de réponse vide"


class _FauxMessage:
    def __init__(self, content):
        self.content = content


class _FauxChoice:
    def __init__(self, content):
        self.message = _FauxMessage(content)


class _FauxChat:
    def __init__(self, content):
        self.choices = [_FauxChoice(content)]


class _FauxGroq:
    """Rend un contenu VIDE, comme gpt-oss-120b en prod."""
    def __init__(self):
        self.appels = 0
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.appels += 1
        return _FauxChat("")


class _FauxNvidia:
    """Échelon suivant : doit être atteint malgré le succès « vide » de Groq."""
    def __init__(self):
        self.appels = 0
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.appels += 1
        return _FauxChat("Wesh ma vie !")


def test_cascade_partagee_descend_apres_une_reponse_vide(monkeypatch):
    import shared.llm_cascade as cascade

    groq, nvidia = _FauxGroq(), _FauxNvidia()
    monkeypatch.setattr(cascade, "get_model_cascade",
                        lambda _t, _bot=None: [("groq", "openai/gpt-oss-120b"),
                                    ("nvidia", "modele/secours")])

    texte = asyncio.run(cascade.generate_response(
        routing={"type": RequestType.TEXT, "reason": "test"},
        system_prompt="sys", transcript="", user_message="coucou",
        conversation_history=[], media_data=None, mime_type="",
        key_manager=None, mistral_client=None,
        groq_client=groq, nvidia_client=nvidia,
        bot_label="Test",
    ))

    assert groq.appels == 1, "Groq devait être tenté"
    assert nvidia.appels == 1, "l'échelon suivant devait être atteint malgré le vide"
    assert texte == "Wesh ma vie !"


def test_cascade_inline_malena_descend_apres_une_reponse_vide(monkeypatch):
    """Malena a sa PROPRE cascade inline : la corriger dans shared/ ne la couvre pas."""
    malena_dir = os.path.join(_parent_dir, "MalenaBot")
    if malena_dir not in sys.path:
        sys.path.insert(0, malena_dir)
    os.environ.setdefault("DISCORD_TOKEN", "dummy")
    bot_malena = pytest.importorskip("bot_malena")

    groq, nvidia = _FauxGroq(), _FauxNvidia()
    monkeypatch.setattr(bot_malena, "get_model_cascade",
                        lambda _t, _bot=None: [("groq", "openai/gpt-oss-120b"),
                                    ("nvidia", "modele/secours")])
    monkeypatch.setattr(bot_malena, "groq_client", groq)
    monkeypatch.setattr(bot_malena, "nvidia_client", nvidia)

    texte = asyncio.run(bot_malena.generate_response_hybrid("coucou"))

    assert groq.appels == 1, "Groq devait être tenté"
    assert nvidia.appels == 1, "l'échelon suivant devait être atteint malgré le vide"
    assert texte == "Wesh ma vie !"
    assert "Erreur API" not in texte


# ---------------------------------------------------------------------------
# Modèles à RAISONNEMENT : la pensée ne doit ni manger le budget de tokens,
# ni atterrir dans la réponse.
# ---------------------------------------------------------------------------

from shared.models import GROQ_FAST, groq_kwargs
from shared.llm_cascade import _fuite_de_raisonnement


def test_groq_kwargs_brident_le_raisonnement_du_modele_de_prod():
    """Mesuré le 2026-08-26 : sans ça, gpt-oss dépense 144 tokens en pensée sur 300,
    et rend un content VIDE dès que le prompt de persona s'allonge."""
    kw = groq_kwargs(GROQ_FAST)
    assert kw.get("reasoning_effort") == "low"
    assert kw.get("reasoning_format") == "hidden", \
        "sans 'hidden', la pensée peut atterrir dans content"


@pytest.mark.parametrize("modele", ["un-modele-sans-raisonnement", "mixtral-8x7b", "", None])
def test_groq_kwargs_ne_touchent_pas_aux_modeles_sans_raisonnement(modele):
    """Passer reasoning_effort à un modèle qui ne raisonne pas ferait un 400."""
    assert groq_kwargs(modele) == {}


class _FauxMessageRaisonneur:
    def __init__(self, content, reasoning=None):
        self.content = content
        self.reasoning = reasoning


_PENSEE = ('Okay, the user sent "benisoubenisou" which seems like a typo or gibberish. '
           'They want me to act as Malena, a gypsy diva from Marseille.')


def test_fuite_de_raisonnement_detecte_la_recopie():
    """Cas réel : nemotron:free recopie sa pensée dans content, tronquée à 300 tokens."""
    msg = _FauxMessageRaisonneur(content=_PENSEE[:300], reasoning=_PENSEE)
    assert _fuite_de_raisonnement(msg) is True


def test_fuite_de_raisonnement_laisse_passer_une_vraie_reponse():
    """Une pensée présente mais une réponse DISTINCTE : c'est le fonctionnement normal."""
    msg = _FauxMessageRaisonneur(content="Wesh ma vie ! 💅", reasoning=_PENSEE)
    assert _fuite_de_raisonnement(msg) is False


@pytest.mark.parametrize("msg", [
    _FauxMessageRaisonneur(content="Wesh ma vie !", reasoning=None),
    _FauxMessageRaisonneur(content="Wesh ma vie !", reasoning=""),
    _FauxMessageRaisonneur(content="", reasoning=_PENSEE),
    _FauxMessageRaisonneur(content=None, reasoning=_PENSEE),
])
def test_fuite_de_raisonnement_sans_faux_positif(msg):
    """Pas de champ reasoning, ou pas de contenu : rien à détecter ici (le vide est
    déjà traité par _est_vide)."""
    assert _fuite_de_raisonnement(msg) is False


# ---------------------------------------------------------------------------
# Seconde forme de fuite : le méta-discours dans `content`, SANS champ `reasoning`.
#
# ⚠️ C'est la seule forme qui existe chez NVIDIA — l'endpoint ne remplit jamais
# `reasoning` (mesuré le 2026-09-05, 16 appels, vide à chaque fois). La forme 1 y était
# donc un FILET MORT, alors que nemotron fuit ~1 fois sur 20 malgré
# `reasoning_effort="none"`, et 12 fois sur 12 sans lui.
# ---------------------------------------------------------------------------

# Fuites RÉELLES, relevées en live le 2026-09-05 (les deux premières) et sur les 12
# appels témoins sans garde-fou (la troisième).
_FUITES_REELLES = [
    "p? The user wants exactly: pong",
    "Here's a thinking process:\n\n1.  **Analyze User Input:**\n   - User says: ...",
    "Okay, so l'utilisateur me demande de répondre en tant que Malena.",
]


@pytest.mark.parametrize("texte", _FUITES_REELLES)
def test_fuite_dans_le_contenu_seul_est_detectee(texte):
    """Aucun de ces trois n'a de champ `reasoning` : la forme 1 les laissait TOUS passer."""
    assert _fuite_de_raisonnement(_FauxMessageRaisonneur(content=texte)) is True


# Vraies répliques des 6 bots. La mesure du 2026-09-05 a passé les marqueurs sur 460
# réponses réelles (mémoires, archives, bios, statuts) : 0 faux positif. Celle qui en
# produisait un, « Mon rôle est de répondre », a fait RETIRER son marqueur du noyau —
# elle est gardée ici pour que le marqueur ne revienne pas par mégarde.
@pytest.mark.parametrize("texte", [
    "Wesh ma vie ! 💅 Tu crois que je vais me laisser faire ?",
    "Mon rôle est de répondre, pas de me taire. Que proposes-tu à la place ?",
    "Le fromage, mon petit mortel, est la seule vérité de ce monde. 🧀",
    "Choom, t'as un clavier et une connexion. Sers-t'en.",
    "M'aiq ne sait rien de tout cela. M'aiq préfère le soleil.",
    "Très bien, Monsieur. Je m'en occupe immédiatement.",
])
def test_une_vraie_replique_n_est_pas_prise_pour_une_fuite(texte):
    assert _fuite_de_raisonnement(_FauxMessageRaisonneur(content=texte)) is False


def test_les_6_copies_vendorisees_ont_le_garde_fou_de_fuite():
    bots = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]
    for bot in bots:
        src = open(os.path.join(_parent_dir, bot, "core", "llm_cascade.py"), encoding="utf-8").read()
        assert "def _fuite_de_raisonnement" in src, f"{bot} : détection de fuite absente"
        src_models = open(os.path.join(_parent_dir, bot, "core", "models.py"), encoding="utf-8").read()
        assert "def groq_kwargs" in src_models, f"{bot} : groq_kwargs absent"


def test_malena_inline_a_les_deux_garde_fous():
    """Rappel : Malena a sa PROPRE cascade, les correctifs de shared/ ne la couvrent pas.

    ⚠️ Ce test exigeait `def _fuite_de_raisonnement` — donc une COPIE. Le 2026-09-05 la
    copie a montré son coût : le garde-fou a gagné une seconde forme de détection (le
    méta-discours dans `content`, la seule qui morde chez NVIDIA) et la copie de Malena
    ne l'aurait jamais eue. Or Malena est justement le bot qui a déjà récité son
    raisonnement en plein Discord. On exige donc l'IMPORT du noyau, l'APPEL, et
    l'ABSENCE de re-définition locale — les trois, sinon un simple import passerait au
    vert sans que la fonction soit branchée.
    """
    src = open(os.path.join(_parent_dir, "MalenaBot", "bot_malena.py"), encoding="utf-8").read()
    assert "from core.llm_cascade import" in src and "_fuite_de_raisonnement" in src, \
        "Malena doit importer le garde-fou du noyau"
    assert "def _fuite_de_raisonnement" not in src, \
        "Malena redéfinit le garde-fou : la copie ne recevra pas les correctifs du noyau"
    assert "_fuite_de_raisonnement(chat.choices[0].message)" in src, \
        "importé mais jamais appelé"
    assert "groq_kwargs(model_name)" in src


# ---------------------------------------------------------------------------
# Un provider qui traîne ne doit pas retenir toute la cascade
# ---------------------------------------------------------------------------

class _FauxGroqLent:
    """Groq sous 429 : le SDK réessaie tout seul avec backoff avant de rendre la main.

    Mesuré en base (data/api_usage.db, sheo, 2026-08-29 et 08-30) : 36205, 37390 et
    36284 ms, toutes en code 429. Pendant ces 36 s la cascade ne basculait pas et le
    bot restait muet, alors que l'échelon suivant répond en une seconde.
    """
    def __init__(self, duree):
        self.duree = duree
        self.appels = 0
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.appels += 1
        import time
        time.sleep(self.duree)
        return _FauxChat("réponse arrivée trop tard")


def test_un_provider_qui_traine_ne_bloque_plus_la_cascade(monkeypatch):
    """Sans borne PAR DÉFAUT, seul JohnnyBot était protégé : les 5 autres bots
    attendaient le provider jusqu'au bout. La borne réelle (15 s) est raccourcie ici
    pour ne pas payer l'attente dans la suite de tests."""
    import shared.llm_cascade as cascade

    monkeypatch.setattr(cascade, "_BORNE_TEXTE", 0.2)
    lent, nvidia = _FauxGroqLent(duree=2.0), _FauxNvidia()
    monkeypatch.setattr(cascade, "get_model_cascade",
                        lambda _t, _bot=None: [("groq", "openai/gpt-oss-120b"),
                                               ("nvidia", "modele/secours")])

    texte = asyncio.run(cascade.generate_response(
        routing={"type": RequestType.TEXT, "reason": "test"},
        system_prompt="sys", transcript="", user_message="coucou",
        conversation_history=[], media_data=None, mime_type="",
        key_manager=None, mistral_client=None,
        groq_client=lent, nvidia_client=nvidia,
        bot_label="Test",
    ))

    assert lent.appels == 1, "Groq devait être tenté"
    assert nvidia.appels == 1, "la cascade devait basculer sans attendre le lent"
    assert texte == "Wesh ma vie !"


def test_l_appelant_garde_la_main_sur_la_borne(monkeypatch):
    """La valeur par défaut ne doit pas écraser un `call_timeout` explicite —
    JohnnyBot en passe un depuis toujours."""
    import shared.llm_cascade as cascade

    monkeypatch.setattr(cascade, "_BORNE_TEXTE", 0.05)
    lent, nvidia = _FauxGroqLent(duree=0.3), _FauxNvidia()
    monkeypatch.setattr(cascade, "get_model_cascade",
                        lambda _t, _bot=None: [("groq", "openai/gpt-oss-120b"),
                                               ("nvidia", "modele/secours")])

    texte = asyncio.run(cascade.generate_response(
        routing={"type": RequestType.TEXT, "reason": "test"},
        system_prompt="sys", transcript="", user_message="coucou",
        conversation_history=[], media_data=None, mime_type="",
        key_manager=None, mistral_client=None,
        groq_client=lent, nvidia_client=nvidia,
        bot_label="Test", call_timeout=5.0,
    ))

    assert nvidia.appels == 0, "la borne explicite a été écrasée par le défaut"
    assert texte == "réponse arrivée trop tard"


def test_un_media_a_droit_a_plus_de_temps_qu_un_tour_de_chat():
    """Donner la borne du texte à une analyse d'image ferait échouer des appels qui
    aboutissaient : Gemini met légitimement plus longtemps sur une pièce jointe."""
    import shared.llm_cascade as cascade
    assert cascade._BORNE_TEXTE > 0, "une borne nulle désarmerait le garde-fou"
    assert cascade._BORNE_MEDIA > cascade._BORNE_TEXTE
    assert cascade._BORNE_TEXTE < 36,         "un 429 Groq coûte 36 s : au-delà, la borne ne sert à rien"
