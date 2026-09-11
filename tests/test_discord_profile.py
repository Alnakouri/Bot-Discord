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


class TestSymboleImporteParLesBots(unittest.TestCase):
    """Verrou : les 6 bots font `from shared.discord_profile import DiscordDailyBio`,
    dans un try/except ImportError qui AVALE la disparition du symbole — la bio
    quotidienne meurt alors en silence, sans une ligne de journal.

    Le 11/09 un module homonyme a ecrase ce fichier entier : import toujours vert,
    fonctionnalite morte sur les 6 bots, suite de tests verte.
    """

    _BOTS = ("Alfred/bot_alfred.py", "JohnnyBot/bot_johnny.py", "MaiqBot/bot_maiq.py",
             "MalenaBot/bot_malena.py", "Sheogorath/bot_sheogorath.py",
             "SugarBot/bot_sugar.py")

    def test_le_symbole_existe_toujours(self):
        import shared.discord_profile as mod
        self.assertTrue(hasattr(mod, "DiscordDailyBio"),
                        "shared/discord_profile.py ne fournit plus DiscordDailyBio : "
                        "les 6 bots retombent silencieusement sur daily_bio = None.")

    def test_les_6_bots_importent_le_symbole(self):
        import ast
        racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for chemin in self._BOTS:
            src = open(os.path.join(racine, chemin), encoding="utf-8").read()
            trouve = any(
                isinstance(n, ast.ImportFrom)
                and n.module == "shared.discord_profile"
                and any(a.name == "DiscordDailyBio" for a in n.names)
                for n in ast.walk(ast.parse(src))
            )
            self.assertTrue(trouve, f"{chemin} n'importe plus DiscordDailyBio")

    def test_les_6_bots_instancient_le_symbole(self):
        import ast
        racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for chemin in self._BOTS:
            src = open(os.path.join(racine, chemin), encoding="utf-8").read()
            trouve = any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "DiscordDailyBio"
                for n in ast.walk(ast.parse(src))
            )
            self.assertTrue(trouve, f"{chemin} n'instancie plus DiscordDailyBio")


if __name__ == "__main__":
    unittest.main()
