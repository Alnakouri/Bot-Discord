# -*- coding: utf-8 -*-
"""Tests unitaires du nettoyage de bio Discord (shared/discord_profile.py).

`_strip_stage_directions` retire didascalies/astérisques et le préfixe « À propos
de moi : » SANS vider une bio entièrement en italique (régression connue corrigée)."""
import os
import sys
import unittest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.discord_profile import DiscordDailyBio

strip = DiscordDailyBio._strip_stage_directions


class TestStripStageDirections(unittest.TestCase):
    def test_plain_text_unchanged(self):
        self.assertEqual(strip("Majordome dévoué et impeccable."),
                         "Majordome dévoué et impeccable.")

    def test_italic_only_is_not_emptied(self):
        # régression : une bio 100% *italique* ne doit PAS devenir vide
        self.assertEqual(strip("*Toujours à votre service.*"),
                         "Toujours à votre service.")

    def test_inline_asterisks_removed(self):
        self.assertEqual(strip("Je suis *vraiment* à votre service."),
                         "Je suis vraiment à votre service.")

    def test_about_me_prefix_removed(self):
        self.assertEqual(strip("À propos de moi : un fou dans un monde sage."),
                         "un fou dans un monde sage.")

    def test_about_me_prefix_case_insensitive(self):
        self.assertEqual(strip("a propos de moi: bonjour"), "bonjour")

    def test_collapses_multiple_spaces(self):
        self.assertIn("service", strip("Toujours    à    votre   service"))
        self.assertNotIn("  ", strip("Toujours    à    votre   service"))

    def test_none_and_empty(self):
        self.assertEqual(strip(None), "")
        self.assertEqual(strip(""), "")


if __name__ == "__main__":
    unittest.main()
