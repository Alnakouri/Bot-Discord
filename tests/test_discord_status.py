# -*- coding: utf-8 -*-
"""Tests unitaires du parseur de statut Discord (shared/discord_status.py).

`_parse_items` extrait une liste [(type, texte)] d'une réponse LLM JSON tolérante :
fences ```…```, texte autour, types en français/majuscules, dédoublonnage, longueur."""
import os
import sys
import unittest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.discord_status import DiscordDailyStatus, MAX_STATUS_LEN, _legacy_to_text

parse = DiscordDailyStatus._parse_items


class TestParseItems(unittest.TestCase):
    def test_plain_json_string_array(self):
        out = parse('["Je fais fondre le caramel 🍬"]')
        self.assertEqual(out, ["Je fais fondre le caramel 🍬"])

    def test_legacy_json_array_conversion(self):
        out = parse('[{"type":"playing","text":"avec le feu"},'
                    '{"type":"watching","text":"la pluie tomber"},'
                    '{"type":"listening","text":"la musique"}]')
        self.assertEqual(out, [
            "Joue avec le feu",
            "Regarde la pluie tomber",
            "Écoute la musique"
        ])

    def test_french_and_uppercase_types_normalized(self):
        out = parse('[{"type":"Regarde","text":"le ciel"},{"type":"ÉCOUTE","text":"les oiseaux"}]')
        self.assertEqual(out, ["Regarde le ciel", "Écoute les oiseaux"])

    def test_code_fences_and_surrounding_text(self):
        out = parse('Voici :\n```json\n["Je joue au ballon"]\n```')
        self.assertEqual(out, ["Je joue au ballon"])

    def test_unknown_type_dropped(self):
        out = parse('[{"type":"streaming","text":"x"},{"type":"playing","text":"y"}]')
        self.assertEqual(out, ["Joue y"])

    def test_empty_text_dropped(self):
        self.assertEqual(parse('[{"type":"playing","text":"  "}]'), [])
        self.assertEqual(parse('["   "]'), [])

    def test_dedup_case_insensitive(self):
        # Pour les chaînes directes
        out = parse('["Caramel", "caramel"]')
        self.assertEqual(out, ["Caramel"])
        # Pour le format hérité converti
        out = parse('[{"type":"playing","text":"Caramel"},{"type":"playing","text":"caramel"}]')
        self.assertEqual(out, ["Joue Caramel"])

    def test_text_truncated(self):
        long = "a" * 200
        out = parse('["%s"]' % long)
        self.assertEqual(len(out[0]), MAX_STATUS_LEN)

    def test_garbage_returns_empty(self):
        self.assertEqual(parse("désolée, pas de JSON ici"), [])
        self.assertEqual(parse(""), [])
        self.assertEqual(parse(None), [])

    def test_not_a_list_returns_empty(self):
        self.assertEqual(parse('{"type":"playing","text":"x"}'), [])


class TestLegacyToText(unittest.TestCase):
    def test_types_and_prefixes(self):
        self.assertEqual(_legacy_to_text("playing", "au foot"), "Joue au foot")
        self.assertEqual(_legacy_to_text("watching", "un film"), "Regarde un film")
        self.assertEqual(_legacy_to_text("listening", "la radio"), "Écoute la radio")

    def test_aliases_and_casing(self):
        self.assertEqual(_legacy_to_text("Regarde", "la TV"), "Regarde la TV")
        self.assertEqual(_legacy_to_text("écoute", "le vent"), "Écoute le vent")

    def test_truncation(self):
        long_text = "x" * 100
        res = _legacy_to_text("playing", long_text)
        self.assertEqual(len(res), MAX_STATUS_LEN)
        self.assertTrue(res.startswith("Joue xx"))


class TestConstructorAndActivity(unittest.TestCase):
    def test_fallback_conversion_in_constructor(self):
        status = DiscordDailyStatus(
            bot=None, bot_id="test_bot", bot_label="Test",
            personality_prompt="Tu es cool.",
            fallback_activities=[("playing", "avec le feu"), ("watching", "des trucs")]
        )
        self.assertEqual(status.fallback_activities, ["Joue avec le feu", "Regarde des trucs"])

    def test_pick_activity_returns_custom_activity(self):
        try:
            import discord
        except ImportError:
            self.skipTest("discord.py non disponible dans l'environnement de test")

        status = DiscordDailyStatus(
            bot=None, bot_id="test_bot", bot_label="Test",
            personality_prompt="Tu es cool.",
            fallback_activities=[("playing", "avec le feu")]
        )
        act = status.pick_activity()
        self.assertIsNotNone(act)
        self.assertIsInstance(act, discord.CustomActivity)
        self.assertEqual(act.name, "Joue avec le feu")


if __name__ == "__main__":
    unittest.main()
