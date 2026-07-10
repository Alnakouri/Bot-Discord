# -*- coding: utf-8 -*-
"""Tests unitaires du garde déterministe `_strip_repeated_opening`
(`shared/twitch/llm.py`) : coupe l'amorce d'une réplique quand elle reprend
l'ouverture d'une réplique récente (moule « Mon jeu préféré ? … »), sans jamais
toucher une ouverture inédite."""
import os
import sys
import unittest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.twitch.llm import _strip_repeated_opening


class TestStripRepeatedOpening(unittest.TestCase):
    def test_repeated_interrogative_preamble_stripped(self):
        # Même préambule interrogatif qu'une réplique récente → on coupe l'amorce en écho.
        recent = ["Mon jeu préféré ? Zelda, toujours et pour la vie."]
        self.assertEqual(
            _strip_repeated_opening("Mon jeu préféré ? Skyrim, évidemment mon sucre.", recent),
            "Skyrim, évidemment mon sucre.",
        )

    def test_novel_opening_untouched(self):
        # Ouverture inédite → jamais modifiée.
        recent = ["Mon jeu préféré ? Zelda, toujours et pour la vie."]
        msg = "Franchement, Skyrim me fait fondre."
        self.assertEqual(_strip_repeated_opening(msg, recent), msg)

    def test_no_recent_untouched(self):
        msg = "Mon jeu préféré ? Skyrim."
        self.assertEqual(_strip_repeated_opening(msg, []), msg)

    def test_empty_reply_untouched(self):
        self.assertEqual(_strip_repeated_opening("", ["Mon jeu préféré ? Zelda."]), "")

    def test_repeated_four_word_opening_without_question(self):
        # Répétition des 4 premiers mots (pas de préambule interrogatif à couper)
        # → détectée comme moule, mais rien à retirer proprement → réplique intacte.
        recent = ["Alors là mon grand, tu rêves."]
        msg = "Alors là mon grand, c'est non."
        self.assertEqual(_strip_repeated_opening(msg, recent), msg)

    def test_short_rest_after_preamble_kept(self):
        # Si le reste après le préambule est trop court (< 15 car.), on ne coupe pas
        # (éviter de renvoyer un moignon).
        recent = ["Mon jeu préféré ? Zelda."]
        msg = "Mon jeu préféré ? Zelda."
        self.assertEqual(_strip_repeated_opening(msg, recent), msg)


if __name__ == "__main__":
    unittest.main()
