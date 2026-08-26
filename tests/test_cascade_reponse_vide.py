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
        for fournisseur in ("GEMINI", "MISTRAL", "GROQ", "OPENROUTER"):
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


class _FauxOpenRouter:
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

    groq, openrouter = _FauxGroq(), _FauxOpenRouter()
    monkeypatch.setattr(cascade, "get_model_cascade",
                        lambda _t: [("groq", "openai/gpt-oss-120b"),
                                    ("openrouter", "modele/secours")])

    texte = asyncio.run(cascade.generate_response(
        routing={"type": RequestType.TEXT, "reason": "test"},
        system_prompt="sys", transcript="", user_message="coucou",
        conversation_history=[], media_data=None, mime_type="",
        key_manager=None, mistral_client=None,
        groq_client=groq, openrouter_client=openrouter,
        bot_label="Test",
    ))

    assert groq.appels == 1, "Groq devait être tenté"
    assert openrouter.appels == 1, "l'échelon suivant devait être atteint malgré le vide"
    assert texte == "Wesh ma vie !"


def test_cascade_inline_malena_descend_apres_une_reponse_vide(monkeypatch):
    """Malena a sa PROPRE cascade inline : la corriger dans shared/ ne la couvre pas."""
    malena_dir = os.path.join(_parent_dir, "MalenaBot")
    if malena_dir not in sys.path:
        sys.path.insert(0, malena_dir)
    os.environ.setdefault("DISCORD_TOKEN", "dummy")
    bot_malena = pytest.importorskip("bot_malena")

    groq, openrouter = _FauxGroq(), _FauxOpenRouter()
    monkeypatch.setattr(bot_malena, "get_model_cascade",
                        lambda _t: [("groq", "openai/gpt-oss-120b"),
                                    ("openrouter", "modele/secours")])
    monkeypatch.setattr(bot_malena, "groq_client", groq)
    monkeypatch.setattr(bot_malena, "openrouter_client", openrouter)

    texte = asyncio.run(bot_malena.generate_response_hybrid("coucou"))

    assert groq.appels == 1, "Groq devait être tenté"
    assert openrouter.appels == 1, "l'échelon suivant devait être atteint malgré le vide"
    assert texte == "Wesh ma vie !"
    assert "Erreur API" not in texte
