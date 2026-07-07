# -*- coding: utf-8 -*-
"""Tests du carnet de rancunes de Sugar (SugarBot/sugar_grudge.py).

Couvre : classification du ton (agression/excuse/gentillesse/priorités),
barème (+2/−2/−1, plafond/plancher), rédemption explicite au retour à 0 par un
GESTE (pas par le temps), décroissance journalière, cooldown anti-spam positif,
messages non adressés ignorés, persistance disque."""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from SugarBot.sugar_grudge import GrudgeBook, classify_tone, MAX_SCORE


class TestClassifyTone(unittest.TestCase):
    def test_insult(self):
        self.assertEqual(classify_tone("espèce de débile"), "aggro")
        self.assertEqual(classify_tone("ta gueule"), "aggro")
        self.assertEqual(classify_tone("t'es vraiment nulle"), "aggro")
        self.assertEqual(classify_tone("tu es trop conne"), "aggro")
        self.assertEqual(classify_tone("je te déteste"), "aggro")

    def test_apology(self):
        self.assertEqual(classify_tone("pardon Sugar"), "apology")
        self.assertEqual(classify_tone("je suis désolé"), "apology")
        self.assertEqual(classify_tone("excuse-moi pour hier"), "apology")

    def test_kind(self):
        self.assertEqual(classify_tone("merci beaucoup !"), "kind")
        self.assertEqual(classify_tone("t'es la meilleure"), "kind")
        self.assertEqual(classify_tone("je t'adore ❤"), "kind")

    def test_aggro_wins_over_apology(self):
        # « désolé mais t'es nulle » = agression, pas excuse
        self.assertEqual(classify_tone("désolé mais t'es nulle"), "aggro")

    def test_neutral(self):
        self.assertEqual(classify_tone("quelle heure il est ?"), "neutral")
        self.assertEqual(classify_tone(""), "neutral")
        self.assertEqual(classify_tone(None), "neutral")

    def test_no_false_positive_on_thing(self):
        # « c'est nul » (parle d'une chose, pas d'elle) ne doit PAS compter
        self.assertEqual(classify_tone("ce jeu c'est nul"), "neutral")


class TestGrudgeBook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "grudge.json")
        # cooldown 0 pour tester les enchaînements sans attendre
        self.book = GrudgeBook(self.path, positive_cooldown=0)

    def tearDown(self):
        self.tmp.cleanup()

    def _score(self, uid="1"):
        return self.book.book[str(uid)]["score"]

    def test_starts_clean(self):
        self.assertEqual(self.book.update("1", "salut !"), "")
        self.assertEqual(self._score(), 0)

    def test_aggression_adds_two(self):
        d = self.book.update("1", "t'es nulle")
        self.assertEqual(self._score(), 2)
        self.assertIn("MÉFIANTE", d)

    def test_score_capped_at_max(self):
        for _ in range(5):
            d = self.book.update("1", "ta gueule")
        self.assertEqual(self._score(), MAX_SCORE)
        self.assertIn("GLACIALE", d)

    def test_kind_removes_one(self):
        self.book.update("1", "t'es nulle")           # 2
        d = self.book.update("1", "merci pour tout")  # 1
        self.assertEqual(self._score(), 1)
        self.assertIn("RADOUCIE", d)

    def test_apology_removes_two_and_redeems(self):
        self.book.update("1", "t'es nulle")        # 2
        d = self.book.update("1", "pardon Sugar")  # 0 → pardon explicite
        self.assertEqual(self._score(), 0)
        self.assertIn("regagner ton pardon", d)

    def test_equilibre_scenario(self):
        # le scénario validé : insulte → excuse → compliment → pardon
        self.book.update("1", "ta gueule sugar")             # 2
        self.book.update("1", "t'es vraiment conne en fait")  # 4
        self.book.update("1", "désolé Sugar")                # 2
        d = self.book.update("1", "t'es la meilleure")       # 1
        self.assertIn("RADOUCIE", d)
        d = self.book.update("1", "merci pour hier")         # 0 → pardon
        self.assertIn("regagner ton pardon", d)
        # le message suivant : plus aucune consigne, pleine douceur
        self.assertEqual(self.book.update("1", "coucou !"), "")

    def test_kindness_does_nothing_at_zero(self):
        d = self.book.update("1", "merci t'es géniale")
        self.assertEqual(self._score(), 0)
        self.assertEqual(d, "")  # pas de « pardon » si rien à pardonner

    def test_not_addressed_ignored(self):
        self.book.update("1", "t'es nulle", addressed=False)
        self.assertEqual(self._score(), 0)
        self.book.update("1", "ta gueule")  # adressé → compte
        self.book.update("1", "merci !", addressed=False)  # pas adressé → ignoré
        self.assertEqual(self._score(), 2)

    def test_positive_cooldown_blocks_spam(self):
        book = GrudgeBook(self.path, positive_cooldown=3600)
        book.update("1", "t'es nulle et conne")  # aggro ×1 → 2... (deux motifs, 1 event)
        self.assertEqual(book.book["1"]["score"], 2)
        book.update("1", "merci !")   # −1 → 1
        book.update("1", "merci !!")  # cooldown → ignoré
        book.update("1", "merci !!!")
        self.assertEqual(book.book["1"]["score"], 1)

    def test_daily_decay(self):
        self.book.update("1", "ta gueule")
        self.book.update("1", "t'es nulle")  # 4
        # simule 3 jours plus tôt
        self.book.book["1"]["last_day"] = str(date.today() - timedelta(days=3))
        d = self.book.update("1", "salut")  # 4 − 3 = 1
        self.assertEqual(self._score(), 1)
        self.assertIn("RADOUCIE", d)

    def test_decay_to_zero_is_silent(self):
        # pardon par le temps = silencieux (pas de phrase de pardon)
        self.book.update("1", "t'es nulle")  # 2
        self.book.book["1"]["last_day"] = str(date.today() - timedelta(days=10))
        d = self.book.update("1", "salut")
        self.assertEqual(self._score(), 0)
        self.assertEqual(d, "")

    def test_persistence(self):
        self.book.update("1", "t'es nulle")
        reloaded = GrudgeBook(self.path)
        self.assertEqual(reloaded.book["1"]["score"], 2)

    def test_users_isolated(self):
        self.book.update("1", "ta gueule")
        self.book.update("2", "merci t'es géniale")
        self.assertEqual(self._score("1"), 2)
        self.assertEqual(self._score("2"), 0)


if __name__ == "__main__":
    unittest.main()
