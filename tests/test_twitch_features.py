# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Inject parent directory to path so dashboard/backend/shared is accessible
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.twitch_chat import setup_twitch_chat
from shared.twitch.game_info import (
    detect_game_question,
    format_facts_block,
    normalize_name,
    get_similarity,
    find_best_match
)

class TestTwitchFeatures(unittest.TestCase):
    def setUp(self):
        self.mock_logger = MagicMock()

    def test_detect_game_question(self):
        # Platform questions
        self.assertEqual(detect_game_question("c'est sur quelle plateforme ?"), "platform")
        self.assertEqual(detect_game_question("dispo sur pc ?"), "platform")
        self.assertEqual(detect_game_question("sur quoi on y joue ?"), "platform")
        
        # Genre questions
        self.assertEqual(detect_game_question("c'est quoi le genre du jeu ?"), "genre")
        self.assertEqual(detect_game_question("c'est un rpg ?"), "genre")
        
        # Studio questions
        self.assertEqual(detect_game_question("qui a developpe ce jeu ?"), "studio")
        self.assertEqual(detect_game_question("quel studio a fait ca ?"), "studio")
        
        # Mode questions
        self.assertEqual(detect_game_question("c'est un jeu coop ?"), "mode")
        self.assertEqual(detect_game_question("on peut y jouer en solo ?"), "mode")
        
        # Release questions
        self.assertEqual(detect_game_question("ca sort quand ?"), "release")
        self.assertEqual(detect_game_question("quelle est la date de sortie ?"), "release")
        
        # About questions
        self.assertEqual(detect_game_question("ca parle de quoi ?"), "about")
        self.assertEqual(detect_game_question("c'est quoi l'histoire ?"), "about")
        
        # Which game questions
        self.assertEqual(detect_game_question("c'est quoi ce jeu ?"), "which_game")
        self.assertEqual(detect_game_question("quel est le nom du jeu ?"), "which_game")
        
        # "pitch" en début de phrase (regex sans espace parasite)
        self.assertEqual(detect_game_question("pitch du jeu ?"), "about")

        # Non-questions
        self.assertIsNone(detect_game_question("salut comment ca va ?"))
        self.assertIsNone(detect_game_question("je joue sur pc aujourd'hui"))

    def test_format_facts_block(self):
        game_data = {
            "name": "The Witcher 3: Wild Hunt",
            "platforms": [{"name": "PC"}, {"name": "PlayStation 4"}, {"name": "Xbox One"}],
            "genres": [{"name": "Role-playing (RPG)"}],
            "first_release_date": 1431907200,  # 2015-05-18
            "summary": "Geralt of Rivia is a witcher, a track downer of monsters for money.",
            "involved_companies": [
                {"company": {"name": "CD Projekt RED"}, "developer": True, "publisher": True}
            ]
        }
        
        # Test Platform
        block_platform = format_facts_block(game_data, "platform")
        self.assertIn("Nom du jeu: The Witcher 3: Wild Hunt", block_platform)
        self.assertIn("Plateformes: PC, PlayStation 4, Xbox One", block_platform)
        self.assertNotIn("Genre:", block_platform)
        
        # Test Studio / Developer
        block_studio = format_facts_block(game_data, "studio")
        self.assertIn("Studio/Developpeur: CD Projekt RED", block_studio)
        self.assertIn("Editeur: CD Projekt RED", block_studio)
        self.assertNotIn("Plateformes:", block_studio)
        
        # Test Release
        block_release = format_facts_block(game_data, "release")
        self.assertIn("Sortie: 2015", block_release)
        self.assertNotIn("Studio/Developpeur:", block_release)

        # Test About
        block_about = format_facts_block(game_data, "about")
        self.assertIn("Resume: Geralt of Rivia is a witcher, a track downer of monsters for money.", block_about)

    def test_find_best_match(self):
        igdb_games = [
            {"id": 1, "name": "Hollow Knight"},
            {"id": 2, "name": "Hollow Knight: Silksong"},
            {"id": 3, "name": "Shovel Knight"}
        ]
        
        match1 = find_best_match("Hollow Knight", igdb_games)
        self.assertIsNotNone(match1)
        self.assertEqual(match1["name"], "Hollow Knight")
        
        match2 = find_best_match("hollow knight silksong", igdb_games)
        self.assertIsNotNone(match2)
        self.assertEqual(match2["name"], "Hollow Knight: Silksong")
        
        match3 = find_best_match("Nonexistent Game Name Here", igdb_games)
        self.assertIsNone(match3)

    @patch.dict(os.environ, {
        "TWITCH_CLIENT_ID": "test_client_id",
        "TWITCH_CLIENT_SECRET": "test_client_secret",
        "TWITCH_BOT_USERNAME": "test_bot_user",
        "TWITCH_OAUTH_TOKEN": "test_oauth_token",
        "TWITCH_CHAT_CHANNELS": "test_channel"
    })
    @patch("shared.twitch_chat._load_dashboard_twitch_config")
    def test_link_commands_registration(self, mock_load_config):
        # Configure dashboard link_commands mock
        mock_load_config.return_value = {
            "link_commands": [
                { "cmd": "discord", "url": "https://discord.gg/test", "label": "Le Discord", "aliases": ["serveur"] },
                { "cmd": "decret", "url": "https://decret-collision", "label": "No decret" },  # Collision with native decret
                { "cmd": "fromage", "url": "https://fromage-reserved" }  # Reserved name
            ]
        }

        native_commands = {
            "decret": lambda author, args: "native decret answer"
        }

        # Initialize TwitchChatBot via setup_twitch_chat
        bot = setup_twitch_chat("johnny", self.mock_logger, commands=native_commands)
        self.assertIsNotNone(bot)
        
        # Verify normal link command registered
        self.assertIn("discord", bot.commands)
        discord_callback = bot.commands["discord"]
        self.assertEqual(discord_callback("author", ""), "Le Discord : https://discord.gg/test")
        
        # Verify alias registered
        self.assertIn("serveur", bot.command_aliases)
        self.assertEqual(bot.command_aliases["serveur"], "discord")
        
        # Verify collision skipped (native command remains untouched)
        self.assertIn("decret", bot.commands)
        self.assertEqual(bot.commands["decret"]("author", ""), "native decret answer")
        
        # Verify reserved name skipped
        self.assertNotIn("fromage", bot.commands)

    @patch.dict(os.environ, {
        "TWITCH_CLIENT_ID": "test_client_id",
        "TWITCH_CLIENT_SECRET": "test_client_secret",
        "TWITCH_BOT_USERNAME": "test_bot_user",
        "TWITCH_OAUTH_TOKEN": "test_oauth_token",
        "TWITCH_CHAT_CHANNELS": "test_channel"
    })
    @patch("shared.twitch_chat._load_dashboard_twitch_config")
    def test_link_command_message_template(self, mock_load_config):
        mock_load_config.return_value = {
            "link_commands": [
                # Template custom valide ({url} seul)
                { "cmd": "yt", "url": "https://youtube.com/test", "message": "Ma chaine : {url}" },
                # Placeholder inconnu → doit etre ignore (sinon .format() planterait au runtime)
                { "cmd": "bad", "url": "https://x", "message": "coucou {pseudo}" },
            ]
        }

        bot = setup_twitch_chat("johnny", self.mock_logger)

        # Template valide pris en compte
        self.assertIn("yt", bot.commands)
        self.assertEqual(bot.commands["yt"]("author", ""), "Ma chaine : https://youtube.com/test")

        # Placeholder inconnu → commande non enregistree
        self.assertNotIn("bad", bot.commands)
