import unittest
import os
import shutil
from pathlib import Path
import sys

# Inject parent directory to path so dashboard/backend is accessible
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Add dashboard/backend to sys.path
backend_dir = os.path.join(_parent_dir, "dashboard", "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from twitch_config import TwitchConfigManager

class TestTwitchConfig(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for test data
        self.test_dir = Path(__file__).parent / "temp_test_data"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.manager = TwitchConfigManager(self.test_dir)

    def tearDown(self):
        # Clean up temp directory
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_extract_login(self):
        # Test raw login names
        self.assertEqual(self.manager.extract_login("ninja"), "ninja")
        self.assertEqual(self.manager.extract_login("Ninja"), "ninja")
        self.assertEqual(self.manager.extract_login("  ninja_123  "), "ninja_123")
        
        # Test valid Twitch URLs
        self.assertEqual(self.manager.extract_login("https://www.twitch.tv/ninja"), "ninja")
        self.assertEqual(self.manager.extract_login("http://twitch.tv/ninja"), "ninja")
        self.assertEqual(self.manager.extract_login("twitch.tv/ninja"), "ninja")
        self.assertEqual(self.manager.extract_login("https://twitch.tv/ninja/profile"), "ninja")
        self.assertEqual(self.manager.extract_login("https://www.twitch.tv/ninja?sr=a"), "ninja")

        # Test invalid inputs
        with self.assertRaises(ValueError):
            self.manager.extract_login("ni")  # too short
        with self.assertRaises(ValueError):
            self.manager.extract_login("a"*26)  # too long
        with self.assertRaises(ValueError):
            self.manager.extract_login("ninja-123")  # contains hyphen
        with self.assertRaises(ValueError):
            self.manager.extract_login("https://google.com")  # wrong domain

    def test_get_all_initializes_defaults(self):
        config = self.manager.get_all()
        # Should initialize defaults for all registry bots
        self.assertIn("johnny", config)
        self.assertIn("maiq", config)
        self.assertIn("sheogorath", config)
        self.assertFalse(config["johnny"]["enabled"])
        self.assertEqual(config["johnny"]["poll_interval_seconds"], 90)
        self.assertEqual(config["johnny"]["subscriptions"], [])

    def test_set_bot_settings(self):
        self.manager.set_bot("johnny", True, 120)
        bot_cfg = self.manager.get_bot("johnny")
        self.assertTrue(bot_cfg["enabled"])
        self.assertEqual(bot_cfg["poll_interval_seconds"], 120)

        # Rejects interval < 60
        with self.assertRaises(ValueError):
            self.manager.set_bot("johnny", True, 45)
            
        # Rejects invalid bot name
        with self.assertRaises(ValueError):
            self.manager.set_bot("nonexistent", True, 90)

    def test_add_and_remove_subscriptions(self):
        # Add a valid subscription
        sub = self.manager.add_subscription("johnny", "https://twitch.tv/shroud", "1234567890", "Live {streamer}!")
        self.assertEqual(sub["twitch_login"], "shroud")
        self.assertEqual(sub["discord_channel_id"], 1234567890)
        self.assertEqual(sub["custom_message"], "Live {streamer}!")
        
        # Verify it is stored and loaded correctly
        bot_cfg = self.manager.get_bot("johnny")
        self.assertEqual(len(bot_cfg["subscriptions"]), 1)
        self.assertEqual(bot_cfg["subscriptions"][0]["twitch_login"], "shroud")

        # Test duplicate prevention
        with self.assertRaises(ValueError):
            self.manager.add_subscription("johnny", "shroud", "1234567890")

        # Test invalid channel ID validation
        with self.assertRaises(ValueError):
            self.manager.add_subscription("johnny", "ninja", "not_an_id")

        # Test invalid message placeholders validation
        with self.assertRaises(ValueError):
            self.manager.add_subscription("johnny", "ninja", "1234567890", "Invalid {place_holder}")

        # Test removing subscription
        self.manager.remove_subscription("johnny", 0)
        bot_cfg = self.manager.get_bot("johnny")
        self.assertEqual(len(bot_cfg["subscriptions"]), 0)

        # Test removing index out of bounds
        with self.assertRaises(ValueError):
            self.manager.remove_subscription("johnny", 0)

    def test_chat_channels(self):
        # Default should be empty list
        config = self.manager.get_all()
        self.assertEqual(config["johnny"]["chat_channels"], [])

        # Update with comma-separated list
        cleaned = self.manager.update_chat_channels("johnny", "ninja, https://twitch.tv/shroud, ")
        self.assertEqual(cleaned, ["ninja", "shroud"])
        
        # Verify it's saved
        bot_cfg = self.manager.get_bot("johnny")
        self.assertEqual(bot_cfg["chat_channels"], ["ninja", "shroud"])

        # Update with list of channels
        cleaned2 = self.manager.update_chat_channels("johnny", ["ninja", "lirik"])
        self.assertEqual(cleaned2, ["ninja", "lirik"])

        # Rejects non-list/non-string
        with self.assertRaises(ValueError):
            self.manager.update_chat_channels("johnny", 123)

        # Rejects invalid twitch channel name
        with self.assertRaises(ValueError):
            self.manager.update_chat_channels("johnny", "ninja, invalid-name")

    def test_update_link_commands_auto(self):
        # 1. auto_minutes 20 conservé, auto_min_messages absent -> 5
        items = self.manager.update_link_commands("johnny", [
            {"cmd": "discord", "url": "https://discord.gg/test", "auto_minutes": 20}
        ])
        self.assertEqual(items[0]["auto_minutes"], 20)
        self.assertEqual(items[0]["auto_min_messages"], 5)

        # 2. absent -> auto_minutes = 0
        items = self.manager.update_link_commands("johnny", [
            {"cmd": "discord", "url": "https://discord.gg/test"}
        ])
        self.assertEqual(items[0]["auto_minutes"], 0)
        self.assertEqual(items[0]["auto_min_messages"], 5)

        # 3. auto_min_messages = 0 accepté
        items = self.manager.update_link_commands("johnny", [
            {"cmd": "discord", "url": "https://discord.gg/test", "auto_minutes": 10, "auto_min_messages": 0}
        ])
        self.assertEqual(items[0]["auto_minutes"], 10)
        self.assertEqual(items[0]["auto_min_messages"], 0)

        # 4. -1 refusé (auto_minutes)
        with self.assertRaises(ValueError):
            self.manager.update_link_commands("johnny", [
                {"cmd": "discord", "url": "https://discord.gg/test", "auto_minutes": -1}
            ])

        # 5. 3 refusé (< 5 min)
        with self.assertRaises(ValueError):
            self.manager.update_link_commands("johnny", [
                {"cmd": "discord", "url": "https://discord.gg/test", "auto_minutes": 3}
            ])

        # 6. "abc" refusé
        with self.assertRaises(ValueError):
            self.manager.update_link_commands("johnny", [
                {"cmd": "discord", "url": "https://discord.gg/test", "auto_minutes": "abc"}
            ])


if __name__ == "__main__":
    unittest.main()
