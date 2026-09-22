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
        self.assertEqual(detect_game_question("c'est quel genre de jeu ?"), "genre")
        self.assertEqual(detect_game_question("c'est quoi comme type de jeu ?"), "genre")

        # ⚠️ « genre » et « type » NUS ne sont pas des questions sur le genre. Les deux
        # seules detections sur 360 messages du chat de #ma_streameuse (22/09) etaient
        # celles-ci : le tic de langage, qui aurait fait repondre « c'est un RPG ».
        self.assertIsNone(detect_game_question("sa baise la genre?"))
        self.assertIsNone(detect_game_question(
            "Mais cest quoi le problème ?genre dire mathilde panot ?"))
        self.assertIsNone(detect_game_question("c'est qui ce type ?"))

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
        # ⚠️ Contrat CHANGÉ le 2026-09-18 : un champ « Message » VIDE ne rend plus le
        # gabarit directement — il fait écrire sa phrase au bot, donc le callback est une
        # coroutine. Le gabarit reste le repli, et ce test le vérifie en awaitant avec un
        # bot dont la cascade ne peut rien rendre (key_manager absent).
        # Le cas « message FOURNI » garde son callback synchrone :
        # cf. test_link_command_message_template.
        import asyncio
        self.assertTrue(asyncio.iscoroutinefunction(discord_callback))
        self.assertEqual(
            asyncio.run(discord_callback("author", "")),
            "Le Discord : https://discord.gg/test",
        )
        
        # Verify alias registered
        self.assertIn("serveur", bot.command_aliases)
        self.assertEqual(bot.command_aliases["serveur"], "discord")
        
        # Verify collision skipped (native command remains untouched)
        self.assertIn("decret", bot.commands)
        self.assertEqual(bot.commands["decret"]("author", ""), "native decret answer")
        
        # Verify reserved name skipped
        self.assertNotIn("fromage", bot.commands)

    def _lignes_info(self):
        """Les messages passes a logger.info, a plat."""
        return [c.args[0] for c in self.mock_logger.info.call_args_list if c.args]

    @patch.dict(os.environ, {
        "TWITCH_CLIENT_ID": "test_client_id",
        "TWITCH_CLIENT_SECRET": "test_client_secret",
        "TWITCH_BOT_USERNAME": "test_bot_user",
        "TWITCH_OAUTH_TOKEN": "test_oauth_token",
        "TWITCH_CHAT_CHANNELS": "test_channel"
    })
    @patch("shared.twitch_chat._load_dashboard_twitch_config")
    def test_link_commands_journalisees_au_demarrage(self, mock_load_config):
        """Ce qui est ARME doit se lire dans le journal.

        Le 22/09 un `!discord` muet a coute une soiree : `link_commands` etait vide et
        RIEN ne le disait — seuls les rejets (collision, nom reserve) se journalisaient.
        Cf. [[gotcha-config-twitch-lue-au-demarrage-seulement]].
        """
        mock_load_config.return_value = {
            "link_commands": [
                {"cmd": "discord", "url": "https://discord.gg/test", "label": "Le Discord",
                 "aliases": ["serveur", "invite"]},
                {"cmd": "tipeee", "url": "https://tipeee.test", "label": "Tipeee",
                 "message": "{label} : {url}"},
            ]
        }
        self.assertIsNotNone(setup_twitch_chat("johnny", self.mock_logger))

        ligne = [l for l in self._lignes_info() if "Commandes de lien armees" in l]
        self.assertEqual(len(ligne), 1, f"une seule ligne attendue, vu : {self._lignes_info()}")
        ligne = ligne[0]
        # La commande, son nombre d'alias, et QUI ecrit la phrase : les trois comptent.
        self.assertIn("!discord", ligne)
        self.assertIn("+2 alias", ligne)
        self.assertIn("phrase du bot", ligne)
        self.assertIn("!tipeee", ligne)
        self.assertIn("gabarit fixe", ligne)

    @patch.dict(os.environ, {
        "TWITCH_CLIENT_ID": "test_client_id",
        "TWITCH_CLIENT_SECRET": "test_client_secret",
        "TWITCH_BOT_USERNAME": "test_bot_user",
        "TWITCH_OAUTH_TOKEN": "test_oauth_token",
        "TWITCH_CHAT_CHANNELS": "test_channel"
    })
    @patch("shared.twitch_chat._load_dashboard_twitch_config")
    def test_aucune_commande_de_lien_se_dit_aussi(self, mock_load_config):
        """Le cas SILENCIEUX — celui qui a mordu — doit etre le plus bavard des deux."""
        mock_load_config.return_value = {"link_commands": []}
        self.assertIsNotNone(setup_twitch_chat("johnny", self.mock_logger))

        ligne = [l for l in self._lignes_info() if "Aucune commande de lien" in l]
        self.assertEqual(len(ligne), 1, f"une seule ligne attendue, vu : {self._lignes_info()}")
        # Le journal doit nommer le FICHIER a corriger, sinon il ne sert a rien.
        self.assertIn("twitch_config.json", ligne[0])

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

    @patch.dict(os.environ, {
        "TWITCH_CLIENT_ID": "test_client_id",
        "TWITCH_CLIENT_SECRET": "test_client_secret",
        "TWITCH_BOT_USERNAME": "test_bot_user",
        "TWITCH_OAUTH_TOKEN": "test_oauth_token",
        "TWITCH_CHAT_CHANNELS": "test_channel"
    })
    @patch("shared.twitch_chat._load_dashboard_twitch_config")
    def test_tone_directive_provider(self, mock_load_config):
        mock_load_config.return_value = {}
        
        provider = MagicMock(return_value="[MOCKED TONE DIRECTIVE]")
        
        bot = setup_twitch_chat(
            "johnny", self.mock_logger,
            tone_directive_provider=provider
        )
        self.assertIsNotNone(bot)
        self.assertEqual(bot.tone_directive_provider, provider)

    def test_truncate_for_twitch(self):
        from shared.twitch.llm import _truncate_for_twitch

        # Court : inchangé
        short = "Petite réplique nette. 😏"
        self.assertEqual(_truncate_for_twitch(short, 480), short)

        # Long : coupe à une fin de phrase, sous la limite, emoji de ton conservé
        long_txt = (
            "Première phrase qui claque et occupe de la place. " * 12
        ).strip() + " 🔪"
        self.assertGreater(len(long_txt), 480)
        out = _truncate_for_twitch(long_txt, 480)
        self.assertLessEqual(len(out), 480)
        self.assertTrue(out.endswith("🔪"))                       # emoji préservé
        self.assertTrue(out.rstrip(" 🔪").endswith("."))          # coupe nette sur une phrase
        self.assertNotIn("Première phrase qui claque et occup ", out)  # jamais coupé en plein mot

        # Aucune fin de phrase ni espace : dernier mot + « … » (jamais en plein mot brut)
        no_boundary = "a" * 600 + " 🧀"
        out2 = _truncate_for_twitch(no_boundary, 480)
        self.assertTrue(out2.endswith("🧀"))
        self.assertIn("…", out2)
