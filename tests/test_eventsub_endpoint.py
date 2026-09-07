# -*- coding: utf-8 -*-
"""L'endpoint EventSub, et la couture qui permet de le simuler.

EventSub ne se déclenche que sur de VRAIS événements de chaîne. Une récompense de points
exige d'être Affilié, d'avoir créé une récompense **personnalisée** (les récompenses
intégrées de Twitch ne déclenchent jamais `...custom_reward_redemption.add`), et un
second compte pour la dépenser. Autant dire que la réaction n'était jamais testée.

La CLI officielle de Twitch sert un serveur EventSub factice ; encore faut-il pouvoir y
pointer le bot. D'où `TWITCH_EVENTSUB_WS_URL`.

⚠️ Ce que ce fichier garde surtout : **la valeur par défaut**. Une couture de test qui
change le comportement de production quand personne ne la règle serait pire que le
manque de test — le bot n'entendrait plus un seul événement réel.
"""
import logging
import sys
from pathlib import Path

import pytest

_racine = Path(__file__).resolve().parent.parent
if str(_racine) not in sys.path:
    sys.path.insert(0, str(_racine))

from shared.twitch_eventsub import WS_URL_TWITCH, _url_websocket  # noqa: E402


class _Journal:
    """Un logger minimal qui garde ce qu'on lui crie."""

    def __init__(self):
        self.avertissements = []

    def warning(self, message):
        self.avertissements.append(message)


def test_sans_variable_c_est_l_endpoint_de_twitch(monkeypatch):
    """⚠️ La garde qui compte le plus : le defaut ne bouge pas."""
    monkeypatch.delenv("TWITCH_EVENTSUB_WS_URL", raising=False)
    journal = _Journal()
    assert _url_websocket(journal) == WS_URL_TWITCH
    assert WS_URL_TWITCH == "wss://eventsub.wss.twitch.tv/ws"
    assert journal.avertissements == [], (
        "Le chemin nominal ne doit rien crier : une alerte pour du nominal est une "
        "alerte qu'on apprend a ignorer."
    )


@pytest.mark.parametrize("valeur", ["", "   "])
def test_une_variable_vide_ne_compte_pas(monkeypatch, valeur):
    """Une variable posee puis videe ne doit pas debrancher le bot de Twitch."""
    monkeypatch.setenv("TWITCH_EVENTSUB_WS_URL", valeur)
    assert _url_websocket(_Journal()) == WS_URL_TWITCH


def test_l_endpoint_substitue_est_pris_en_compte(monkeypatch):
    monkeypatch.setenv("TWITCH_EVENTSUB_WS_URL", "ws://host.docker.internal:8080/ws")
    assert _url_websocket(_Journal()) == "ws://host.docker.internal:8080/ws"


def test_une_substitution_ne_se_fait_JAMAIS_en_silence(monkeypatch):
    """⚠️ Un bot branche sur un serveur factice n'entend plus un evenement reel.

    Oubliee, la variable rendrait EventSub definitivement muet — sans erreur, sans
    trace. Exactement le piege de l'echelon invisible. La substitution s'annonce.
    """
    monkeypatch.setenv("TWITCH_EVENTSUB_WS_URL", "ws://127.0.0.1:8080/ws")
    journal = _Journal()
    _url_websocket(journal)
    assert len(journal.avertissements) == 1
    dit = journal.avertissements[0]
    assert "ws://127.0.0.1:8080/ws" in dit, "l'alerte doit nommer l'endroit reel"
    assert "reel" in dit.lower(), "l'alerte doit dire ce qu'on perd"


def test_le_defaut_du_journal_est_le_logger_du_module(monkeypatch):
    """Appele sans journal (outils, sondes), il ne doit pas lever."""
    monkeypatch.setenv("TWITCH_EVENTSUB_WS_URL", "ws://127.0.0.1:8080/ws")
    assert _url_websocket() == "ws://127.0.0.1:8080/ws"


def test_le_client_lit_l_endpoint_a_la_construction(monkeypatch):
    """La couture ne vaut que si le client s'en sert vraiment."""
    from shared.twitch_eventsub import TwitchEventSub

    monkeypatch.setenv("TWITCH_EVENTSUB_WS_URL", "ws://host.docker.internal:8080/ws")
    client = TwitchEventSub(
        bot_id="sheogorath", logger=logging.getLogger("test"), auth=None,
        client_id="x", broadcaster_id="1", emit_callback=None, subscriptions=[],
    )
    assert client.ws_url == "ws://host.docker.internal:8080/ws"
