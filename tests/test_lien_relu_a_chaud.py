# -*- coding: utf-8 -*-
"""Verrou : un lien change dans le dashboard sert au `!discord` suivant, sans redemarrer.

24/11/2026 : l'invitation de Sugar expirait, le proprietaire en a cree une permanente
dans le dashboard... et Sugar a continue de donner l'ancienne jusqu'au redemarrage du
conteneur, parce que les commandes de lien sont construites une seule fois. L'adresse
est maintenant relue a chaque appel (`_lien_a_jour`), pour les deux formes de commande :
gabarit fixe et phrase ecrite par le bot.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from shared.twitch_chat import setup_twitch_chat

ENV = {
    "TWITCH_CLIENT_ID": "test_client_id",
    "TWITCH_CLIENT_SECRET": "test_client_secret",
    "TWITCH_BOT_USERNAME": "test_bot_user",
    "TWITCH_OAUTH_TOKEN": "test_oauth_token",
    "TWITCH_CHAT_CHANNELS": "ma_streameuse",
}
ANCIEN = "https://discord.gg/ancien"
NOUVEAU = "https://discord.gg/permanent"


def _monter(entree):
    """Un bot construit avec `entree`, et la config vivante que le test peut modifier."""
    config = {"link_commands": [dict(entree)]}
    patcher = patch("shared.twitch_chat._load_dashboard_twitch_config", side_effect=lambda *a: config)
    patcher.start()
    with patch.dict(os.environ, ENV):
        bot = setup_twitch_chat("sugar", MagicMock())
    return bot, config, patcher


def test_le_gabarit_fixe_suit_le_lien_change():
    bot, config, patcher = _monter({"cmd": "discord", "url": ANCIEN, "message": "Viens : {url}"})
    try:
        assert bot.commands["discord"]("bob", "") == f"Viens : {ANCIEN}"
        config["link_commands"][0]["url"] = NOUVEAU
        assert bot.commands["discord"]("bob", "") == f"Viens : {NOUVEAU}"
    finally:
        patcher.stop()


def test_la_phrase_du_bot_recoit_le_lien_change():
    bot, config, patcher = _monter({"cmd": "discord", "url": ANCIEN, "label": "discord"})
    vus = []

    async def _phrase(cmd, label, url):
        vus.append(url)
        return f"Rejoins-moi. {url}"

    bot._generate_link_line = _phrase
    try:
        config["link_commands"][0]["url"] = NOUVEAU
        assert asyncio.run(bot.commands["discord"]("bob", "")) == f"Rejoins-moi. {NOUVEAU}"
        assert vus == [NOUVEAU]
    finally:
        patcher.stop()


def test_le_changement_n_est_journalise_qu_une_fois():
    bot, config, patcher = _monter({"cmd": "discord", "url": ANCIEN, "message": "{url}"})
    try:
        config["link_commands"][0]["url"] = NOUVEAU
        for _ in range(3):
            bot.commands["discord"]("bob", "")
        # Le journal du bot est celui passe a setup_twitch_chat.
        lignes = [c.args[0] for c in bot.logger.info.call_args_list if "relu à chaud" in str(c.args[0])]
        assert len(lignes) == 1 and NOUVEAU in lignes[0]
    finally:
        patcher.stop()


def test_une_commande_retiree_ou_videe_garde_le_lien_du_demarrage():
    # Un lien vide serait pire qu'un lien ancien : le viewer attend une adresse.
    bot, config, patcher = _monter({"cmd": "discord", "url": ANCIEN, "message": "{url}"})
    try:
        config["link_commands"][0]["url"] = ""
        assert bot.commands["discord"]("bob", "") == ANCIEN
        config["link_commands"] = []
        assert bot.commands["discord"]("bob", "") == ANCIEN
    finally:
        patcher.stop()
