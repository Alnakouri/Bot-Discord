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

from shared.twitch.llm import (
    _strip_repeated_opening,
    _build_anti_tic_consigne,
    _strip_echo_opening,
)


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


class TestBuildAntiTicConsigne(unittest.TestCase):
    def test_empty_or_none(self):
        self.assertEqual(_build_anti_tic_consigne(None), "")
        self.assertEqual(_build_anti_tic_consigne([]), "")
        self.assertEqual(_build_anti_tic_consigne(["", None, "   "]), "")

    def test_extracts_amorces_and_clotures(self):
        recent = [
            "Bonjour mon cher mortel ! J'adore le fromage. 🧀",
            "Silence, ver de terre ! Haskill, apporte les cuillères. 🥄",
        ]
        consigne = _build_anti_tic_consigne(recent)
        self.assertIn("[ANTI-TICS — VARIE OU MEURS]", consigne)
        self.assertIn('"bonjour mon cher mortel j\'adore"', consigne)
        self.assertIn('"silence ver de terre haskill"', consigne)
        # Clôtures : dernière phrase, emoji retiré
        self.assertIn('"j\'adore le fromage"', consigne)
        self.assertIn('"haskill apporte les cuillères"', consigne)

    def test_dedup(self):
        # Deux répliques dont les 5 premiers mots sont identiques → amorce listée une seule fois.
        recent = [
            "Toujours la même rengaine avec toi, franchement.",
            "Toujours la même rengaine avec vous, décidément.",
        ]
        consigne = _build_anti_tic_consigne(recent)
        self.assertEqual(consigne.count('"toujours la même rengaine avec"'), 1)


class TestStripEchoOpening(unittest.TestCase):
    """Parité Twitch du garde Discord : tue l'ouverture-perroquet HURLÉE, épargne le reste."""

    def test_shouted_echo_stripped(self):
        # Sheo ouvre en hurlant l'insulte du viewer → on coupe, on garde la vanne.
        reply = 'Oh, "FACE DE PET" ! Quelle poésie. Retourne ramper sous ta pierre, cloporte.'
        out = _strip_echo_opening(reply, "sheo la face de pet")
        self.assertNotIn("FACE DE PET", out)
        self.assertIn("cloporte", out)

    def test_pure_interjection_stripped(self):
        reply = "Ah... Tu crois vraiment m'atteindre avec ça, pauvre mortel ?"
        out = _strip_echo_opening(reply, "çava tete de cul ?")
        self.assertTrue(out.startswith("Tu crois"))

    def test_normal_case_echo_preserved(self):
        # Écho en casse normale = réflexion voulue, canon → intact.
        reply = "Des pâtes ? Excellent choix pour un mortel sans imagination."
        self.assertEqual(_strip_echo_opening(reply, "j'ai mangé des pâtes"), reply)

    def test_all_caps_reply_preserved(self):
        reply = "TAIS-TOI, INSECTE, AVANT QUE JE T'ÉCRASE."
        self.assertEqual(_strip_echo_opening(reply, "sheo tais toi"), reply)

    def test_no_stub_left(self):
        # Ne coupe jamais si le reste devient un moignon.
        reply = "NUL ?! Ha."
        self.assertEqual(_strip_echo_opening(reply, "tu es nul"), reply)

    def test_empty_inputs(self):
        self.assertEqual(_strip_echo_opening("", "insulte"), "")
        self.assertEqual(_strip_echo_opening("Une réponse.", ""), "Une réponse.")


if __name__ == "__main__":
    unittest.main()
