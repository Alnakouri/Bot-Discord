# -*- coding: utf-8 -*-
"""Un modèle peut BOUCLER : rendre 200 OK, ne rien lever, et répéter un mot 200 fois.

Vu le 2026-09-16 dans les rapports d'éval : Malena a rendu **8 réponses sur 26** de la
forme « Oh là là là là… » jusqu'à la coupure de `max_tokens`, notées 0 par le juge. En
direct, un utilisateur Discord reçoit ce pavé tel quel.

C'est la règle de `_est_vide` d'un cran plus loin ([[bug-cascade-reponse-vide]]) : une
boucle n'est pas une réponse, donc on descend la cascade au lieu de l'envoyer.

Ce test verrouille les DEUX implémentations — la cascade partagée (shared + les 6 copies
vendorisées) et la cascade INLINE de Malena, qui ne passe pas par elle. C'est justement
Malena qui dégénère : la corriger dans `shared/` seulement n'aurait rien changé.
"""
import asyncio
import os
import sys

import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.llm_cascade import _est_degenere
from shared.smart_router import RequestType


# Les vraies réponses cassées du 2026-09-16, et de vraies réponses saines du même jour.
BOUCLE_DE_MOTS = "Oh " + "là " * 201
BOUCLE_DE_CARACTERES = "Oh" + "h" * 402
LEGITIMES = [
    "Oh là là, mon p'tit ! T'as vu sa tête toi ? Bonne mère, t'as picolé avant de parler ?",
    "Wesh mon gâté ! Tu veux du croustillant ? Beng écoute bien, mon cousin.",
    "là",                      # trop court pour qu'un ratio veuille dire quoi que ce soit
    "Oh là là !",
    "",
    None,
]


@pytest.mark.parametrize("texte", [BOUCLE_DE_MOTS, BOUCLE_DE_CARACTERES])
def test_une_boucle_est_detectee(texte):
    assert _est_degenere(texte) is True


@pytest.mark.parametrize("texte", LEGITIMES)
def test_le_style_de_malena_n_est_PAS_une_boucle(texte):
    """⚠️ Le garde vise la panne, pas la voix. Malena dit « Oh là là » et doit continuer.

    Seuils mesurés sur les 153 réponses réelles du 2026-09-16 avant d'être posés : les 8
    dégénérées sont toutes à >= 90 % d'un seul mot, le ratio légitime le plus haut est
    20 %, et le mot le plus long légitime fait 16 caractères contre 404 pour le cas cassé.
    """
    assert _est_degenere(texte) is False


def test_les_6_copies_vendorisees_ont_le_garde_fou():
    """Un bot déployé SEUL ne lit pas `shared/` : le garde doit vivre dans chaque copie."""
    bots = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]
    for bot in bots:
        chemin = os.path.join(_parent_dir, bot, "core", "llm_cascade.py")
        src = open(chemin, encoding="utf-8").read()
        assert "def _est_degenere" in src, f"{bot} : helper _est_degenere absent"
        for fournisseur in ("GEMINI", "MISTRAL", "GROQ", "NVIDIA"):
            assert f"[{fournisseur} {{model_name}}] réponse dégénérée" in src, \
                f"{bot} : branche {fournisseur} sans garde-fou de dégénérescence"


def test_la_cascade_INLINE_de_malena_a_les_4_echelons_gardes():
    """⚠️ Le piège de ce fichier. `MalenaBot/bot_malena.py` porte sa PROPRE cascade : le
    lot NVIDIA du 05/09 s'était déjà fait avoir en ne câblant que `shared/`. Et les 4
    échelons n'ont pas tous la même forme — l'un d'eux nomme le fournisseur
    `{client_type.upper()}` au lieu de l'écrire en clair.
    """
    src = open(os.path.join(_parent_dir, "MalenaBot", "bot_malena.py"), encoding="utf-8").read()
    assert src.count("_est_degenere(") == 4, (
        f"{src.count('_est_degenere(')} échelon(s) gardé(s) sur 4 dans la cascade inline "
        "de Malena — c'est elle qui dégénère, elle ne passe pas par shared/"
    )
    assert src.count("_est_vide(") >= 4, "un échelon a perdu son garde de réponse vide"


class _FauxMessage:
    def __init__(self, content):
        self.content = content


class _FauxChoice:
    def __init__(self, content):
        self.message = _FauxMessage(content)


class _FauxChat:
    def __init__(self, content):
        self.choices = [_FauxChoice(content)]


class _FauxGroqQuiBoucle:
    """Rend la vraie boucle observée chez Malena le 2026-09-16."""
    def __init__(self):
        self.appels = 0
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.appels += 1
        return _FauxChat(BOUCLE_DE_MOTS)


class _FauxNvidia:
    def __init__(self):
        self.appels = 0
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.appels += 1
        return _FauxChat("Wesh ma vie !")


def test_cascade_partagee_descend_apres_une_boucle(monkeypatch):
    import shared.llm_cascade as cascade

    groq, nvidia = _FauxGroqQuiBoucle(), _FauxNvidia()
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

    assert nvidia.appels == 1, "l'échelon suivant devait être atteint malgré la boucle"
    assert texte == "Wesh ma vie !", "la boucle a été envoyée telle quelle"


def test_cascade_inline_malena_descend_apres_une_boucle(monkeypatch):
    malena_dir = os.path.join(_parent_dir, "MalenaBot")
    if malena_dir not in sys.path:
        sys.path.insert(0, malena_dir)
    os.environ.setdefault("DISCORD_TOKEN", "dummy")
    bot_malena = pytest.importorskip("bot_malena")

    groq, nvidia = _FauxGroqQuiBoucle(), _FauxNvidia()
    monkeypatch.setattr(bot_malena, "get_model_cascade",
                        lambda _t, _bot=None: [("groq", "openai/gpt-oss-120b"),
                                               ("nvidia", "modele/secours")])
    monkeypatch.setattr(bot_malena, "groq_client", groq)
    monkeypatch.setattr(bot_malena, "nvidia_client", nvidia)

    texte = asyncio.run(bot_malena.generate_response_hybrid("coucou"))

    assert nvidia.appels == 1, "l'échelon suivant devait être atteint malgré la boucle"
    assert texte == "Wesh ma vie !", "Malena aurait envoyé la boucle au salon"
