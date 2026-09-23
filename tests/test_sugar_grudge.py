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

    def test_insult_crude(self):
        # Insultes crues courantes qui manquaient (cf. test live « tete de cul » non détecté)
        for msg in ["tete de cul", "tête de cul", "enfoiré", "enculé", "bâtard",
                    "fdp", "ntm", "fils de pute", "trou du cul", "va te faire foutre", "gros con"]:
            self.assertEqual(classify_tone(msg), "aggro", msg)

    def test_insult_no_false_positive(self):
        # Ne PAS confondre avec du vocabulaire anodin/sucré
        for msg in ["ta culotte est jolie", "concours de cuisine", "un gros gâteau au caramel"]:
            self.assertNotEqual(classify_tone(msg), "aggro", msg)

    def test_apology(self):
        self.assertEqual(classify_tone("pardon Sugar"), "apology")
        self.assertEqual(classify_tone("je suis désolé"), "apology")
        self.assertEqual(classify_tone("excuse-moi pour hier"), "apology")

    def test_kind(self):
        self.assertEqual(classify_tone("merci beaucoup !"), "kind")
        self.assertEqual(classify_tone("t'es la meilleure"), "kind")
        self.assertEqual(classify_tone("je t'adore ❤"), "kind")

    def test_kind_slang(self):
        # Amical élargi (slang) : doit router vers « kind » (ton chaleureux)
        for msg in ["quel acceuil sucré bg", "t'es sympa toi", "trop cool merci",
                    "au top !", "t'es chaleureuse", "magnifique", "canon", "ma reine"]:
            self.assertEqual(classify_tone(msg), "kind", msg)

    def test_kind_negation_not_kind(self):
        # « pas cool / pas sympa » ne sont PAS des gentillesses
        self.assertEqual(classify_tone("c'est pas cool"), "neutral")
        self.assertEqual(classify_tone("pas sympa du tout"), "neutral")

    def test_aggro_wins_over_kind_slang(self):
        # une insulte l'emporte sur un « bg » amical
        self.assertEqual(classify_tone("ta gueule bg"), "aggro")

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
        # Tous les délais à 0 pour tester les enchaînements sans attendre : le barème
        # (+2 par offense, −2/−1 par geste) se mesure ici, ses garde-fous de temps ont
        # leurs propres tests dans TestGrudgeRythme.
        self.book = GrudgeBook(self.path, positive_cooldown=0, apology_cooldown=0,
                               aggro_window=0)

    def tearDown(self):
        self.tmp.cleanup()

    def _score(self, uid="1"):
        return self.book.book[str(uid)]["score"]

    def test_starts_clean(self):
        # Aucune rancune ne fuit (une simple consigne [TON] chaleureuse est permise).
        self.assertNotIn("CARNET", self.book.update("1", "salut !"))
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

    def test_crude_insult_drives_redemption_arc(self):
        # Régression du test live : « tete de cul » DOIT monter la rancune (avant :
        # classé neutre → l'excuse n'avait rien à pardonner, rédemption jamais déclenchée).
        d1 = self.book.update("1", "tete de cul")
        self.assertEqual(self._score(), 2)
        self.assertIn("MÉFIANTE", d1)
        d2 = self.book.update("1", "désolé je m'excuse")
        self.assertEqual(self._score(), 0)
        self.assertIn("regagner ton pardon", d2)  # rédemption explicite

    def test_equilibre_scenario(self):
        # le scénario validé : insulte → excuse → compliment → pardon
        self.book.update("1", "ta gueule sugar")             # 2
        self.book.update("1", "t'es vraiment conne en fait")  # 4
        self.book.update("1", "désolé Sugar")                # 2
        d = self.book.update("1", "t'es la meilleure")       # 1
        self.assertIn("RADOUCIE", d)
        d = self.book.update("1", "merci pour hier")         # 0 → pardon
        self.assertIn("regagner ton pardon", d)
        # le message suivant : plus aucune rancune, pleine douceur (pas de carnet)
        self.assertNotIn("CARNET", self.book.update("1", "coucou !"))

    def test_kindness_does_nothing_at_zero(self):
        d = self.book.update("1", "merci t'es géniale")
        self.assertEqual(self._score(), 0)
        self.assertNotIn("CARNET", d)  # pas de « pardon » si rien à pardonner (un [TON] chaleureux est permis)

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
        self.assertNotIn("CARNET", d)  # pardon par le temps = silencieux (aucune mention du carnet)

    def test_persistence(self):
        self.book.update("1", "t'es nulle")
        reloaded = GrudgeBook(self.path)
        self.assertEqual(reloaded.book["1"]["score"], 2)

    def test_users_isolated(self):
        self.book.update("1", "ta gueule")
        self.book.update("2", "merci t'es géniale")
        self.assertEqual(self._score("1"), 2)
        self.assertEqual(self._score("2"), 0)


class TestSugarGrudgeLLM(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "grudge_llm.json")
        self.book = GrudgeBook(self.path, positive_cooldown=0, llm_enabled=True,
                               apology_cooldown=0, aggro_window=0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_llm_tone(self):
        self.assertEqual(GrudgeBook.parse_llm_tone("AGGRO"), "aggro")
        self.assertEqual(GrudgeBook.parse_llm_tone("aggro."), "aggro")
        self.assertEqual(GrudgeBook.parse_llm_tone("Réponse : GENTIL"), "neutral")
        self.assertEqual(GrudgeBook.parse_llm_tone("NEUTRE\n"), "neutral")
        self.assertEqual(GrudgeBook.parse_llm_tone("charabia"), "neutral")
        self.assertEqual(GrudgeBook.parse_llm_tone(""), "neutral")
        self.assertEqual(GrudgeBook.parse_llm_tone(None), "neutral")
        self.assertEqual(GrudgeBook.parse_llm_tone("GENTIL et beau"), "kind")
        self.assertEqual(GrudgeBook.parse_llm_tone("EXCUSE"), "apology")

    def test_apply_event(self):
        # Starts at 0
        self.book.apply_event("1", "aggro")
        self.assertEqual(self.book.book["1"]["score"], 2)
        # Cap max
        self.book.apply_event("1", "aggro")
        self.book.apply_event("1", "aggro")
        self.assertEqual(self.book.book["1"]["score"], 5)
        # apology removes 2
        self.book.apply_event("1", "apology")
        self.assertEqual(self.book.book["1"]["score"], 3)
        # kind removes 1
        self.book.apply_event("1", "kind")
        self.assertEqual(self.book.book["1"]["score"], 2)
        # neutral does nothing
        self.book.apply_event("1", "neutral")
        self.assertEqual(self.book.book["1"]["score"], 2)
        # apology to 0
        redeemed = self.book.apply_event("1", "apology")
        self.assertTrue(redeemed)
        self.assertEqual(self.book.book["1"]["score"], 0)

    def test_should_refine(self):
        # False si lexique non-neutral
        self.assertFalse(self.book.should_refine("1", "t'es nulle", "aggro"))
        # False si llm_enabled=False
        book_disabled = GrudgeBook(self.path, llm_enabled=False)
        self.assertFalse(book_disabled.should_refine("1", "quelque chose", "neutral"))

        # False sur message d'un seul mot
        self.assertFalse(self.book.should_refine("1", "mot", "neutral"))

        # False à score 0 sans marqueur 2e personne
        self.assertFalse(self.book.should_refine("1", "bonjour comment ca va", "neutral"))
        # True à score 0 avec « t'es … » or « tu » or « sugar »
        self.assertTrue(self.book.should_refine("1", "t'es qui ?", "neutral"))
        self.assertTrue(self.book.should_refine("1", "tu me boudes ?", "neutral"))

        # True à score > 0 sur message neutre (même sans 2e personne)
        self.book.book["1"] = {"score": 2, "last_day": str(date.today()), "last_positive_ts": 0.0}
        self.assertTrue(self.book.should_refine("1", "quelque chose", "neutral"))

        # False sous cooldown 60 s
        import time
        self.book.book["1"]["last_llm_ts"] = time.time() - 30
        self.assertFalse(self.book.should_refine("1", "quelque chose", "neutral"))
        # True après cooldown
        self.book.book["1"]["last_llm_ts"] = time.time() - 61
        self.assertTrue(self.book.should_refine("1", "quelque chose", "neutral"))

    async def test_refine_async(self):
        # Fake llm_call returning AGGRO
        async def fake_llm_aggro(system_prompt, user_message):
            return "AGGRO"

        # Start score at 0
        self.assertEqual(self.book.book.get("1", {}).get("score", 0), 0)
        # Call refine_async on a text with marker so should_refine is True
        await self.book.refine_async("1", "tu es bizarre", fake_llm_aggro)
        self.assertEqual(self.book.book["1"]["score"], 2)

        # Fake GENTIL à score 1 -> pending_redemption posé
        self.book.book["1"]["score"] = 1
        # Clear cooldown so should_refine passes
        self.book.book["1"]["last_llm_ts"] = 0.0
        async def fake_llm_gentil(system_prompt, user_message):
            return "GENTIL"
        await self.book.refine_async("1", "tu es gentille", fake_llm_gentil)
        self.assertEqual(self.book.book["1"]["score"], 0)
        self.assertTrue(self.book.book["1"].get("pending_redemption"))

        # puis update() suivant (message non agressif) -> renvoie la directive de pardon UNE fois puis plus rien
        d1 = self.book.update("1", "bonjour", addressed=True)
        self.assertIn("regagner ton pardon", d1)
        self.assertNotIn("pending_redemption", self.book.book["1"])

        d2 = self.book.update("1", "re-bonjour", addressed=True)
        self.assertNotIn("CARNET", d2)  # la directive de pardon ne se répète pas

        # Test: update() suivant agressif -> flag consommé silencieusement + score +2
        self.book.book["1"]["score"] = 1
        self.book.book["1"]["last_llm_ts"] = 0.0
        await self.book.refine_async("1", "tu es gentille", fake_llm_gentil)
        self.assertEqual(self.book.book["1"]["score"], 0)
        self.assertTrue(self.book.book["1"].get("pending_redemption"))
        # Current message is aggro
        d_aggro = self.book.update("1", "t'es nulle", addressed=True)
        self.assertNotIn("pending_redemption", self.book.book["1"])
        self.assertEqual(self.book.book["1"]["score"], 2)
        self.assertIn("MÉFIANTE", d_aggro)

        # fake LLM qui lève une exception -> aucun crash, score inchangé
        async def fake_llm_error(system_prompt, user_message):
            raise Exception("API Error")
        self.book.book["1"]["last_llm_ts"] = 0.0
        await self.book.refine_async("1", "tu es bizarre", fake_llm_error) # No exception raised
        self.assertEqual(self.book.book["1"]["score"], 2)

        # fake « NEUTRE » -> aucun save/changement
        async def fake_llm_neutre(system_prompt, user_message):
            return "NEUTRE"
        self.book.book["1"]["last_llm_ts"] = 0.0
        await self.book.refine_async("1", "tu es bizarre", fake_llm_neutre)
        self.assertEqual(self.book.book["1"]["score"], 2)

    def test_persistence_of_pending_redemption(self):
        self.book.book["1"] = {
            "score": 0,
            "last_day": str(date.today()),
            "last_positive_ts": 0.0,
            "pending_redemption": True
        }
        self.book._save()

        reloaded = GrudgeBook(self.path)
        self.assertTrue(reloaded.book["1"].get("pending_redemption"))


class TestToneDirective(unittest.TestCase):
    def test_tone_directive(self):
        from SugarBot.sugar_grudge import tone_directive
        
        # Test kind text
        kind_dir = tone_directive("bg t es trop cool")
        self.assertTrue(kind_dir.startswith("\n[TON] Cette personne est gentille"))
        
        # Test neutral text
        neutral_dir = tone_directive("quel temps fait-il ?")
        self.assertTrue(neutral_dir.startswith("\n[TON] Message neutre"))
        
        # Test apology text
        self.assertTrue(tone_directive("dsl").startswith("\n[TON] Cette personne s'excuse"))

        # Test aggro text (returns empty string)
        self.assertEqual(tone_directive("ferme la"), "")
        self.assertEqual(tone_directive("t'es nulle"), "")

    def test_verrou_mots_interdits_dans_directive_neutre(self):
        from SugarBot.sugar_grudge import _DIRECTIVE_NEUTRAL
        for mot in ("longueur", "orthographe", "minuscules"):
            self.assertNotIn(mot, _DIRECTIVE_NEUTRAL.lower())

    def test_grudgebook_apology_sans_rancune(self):
        import tempfile
        from SugarBot.sugar_grudge import GrudgeBook, _DIRECTIVE_APOLOGY
        with tempfile.TemporaryDirectory() as tmp:
            book_path = os.path.join(tmp, "grudge.json")
            book = GrudgeBook(book_path, llm_enabled=False)
            directive = book.update(12345, "désolé")
            self.assertEqual(directive, _DIRECTIVE_APOLOGY)


class TestGrudgeRythme(unittest.TestCase):
    """Le RYTHME du carnet : ce qui compte pour une offense, et ce qui relâche.

    Défaut mesuré en test live le 2026-09-07 : six insultes d'affilée pour éprouver
    la répartie de Sugar, puis « dsl je m'excuse » — et elle répond encore « peteur ».

    Deux causes, toutes deux de temps :
      * chaque message d'une même rafale valait +2, donc le carnet était au plafond ;
      * l'excuse partageait le cooldown de 10 minutes des « merci », prévu contre le
        spam de gentillesses : la première excuse comptait, les suivantes non.
    Le carnet durcissait sans jamais se relâcher.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "grudge_rythme.json")
        self.book = GrudgeBook(self.path)      # les vrais réglages, c'est le sujet

    def tearDown(self):
        self.tmp.cleanup()

    def _score(self):
        return self.book.book["1"]["score"]

    def test_le_scenario_live_du_2026_09_07(self):
        """Six insultes d'affilée, puis une excuse : le pardon doit être accordé."""
        for insulte in ["t'es nulle", "ta gueule", "espèce de débile",
                        "tu sers à rien", "t'es vraiment conne", "dégage"]:
            self.book.update("1", insulte, addressed=True)
        self.assertEqual(self._score(), 2,
                         "une rafale d'insultes est UN emportement, pas six offenses")

        directive = self.book.update("1", "dsl je m'excuse", addressed=True)
        self.assertEqual(self._score(), 0)
        self.assertIn("regagner ton pardon", directive,
                      "après une excuse, Sugar doit accorder son pardon explicitement")

    def test_une_offense_plus_tard_recompte(self):
        """La fenêtre ne pardonne pas : elle refuse seulement de compter deux fois."""
        self.book.update("1", "t'es nulle", addressed=True)
        self.assertEqual(self._score(), 2)
        # Même personne, mais l'emportement d'avant est passé.
        self.book.book["1"]["last_aggro_ts"] = 0.0
        self.book.update("1", "ta gueule", addressed=True)
        self.assertEqual(self._score(), 4, "une nouvelle offense doit bien re-monter")

    def test_une_excuse_n_est_pas_bloquee_par_un_merci_recent(self):
        """⚠️ Le cœur du défaut : deux horloges, pas une.

        Un « merci » d'il y a cinq minutes ne doit pas rendre une excuse sans effet.
        """
        self.book.update("1", "t'es nulle", addressed=True)          # 2
        self.book.update("1", "merci quand même", addressed=True)    # 1, pose l'horloge kind
        self.assertEqual(self._score(), 1)
        self.book.update("1", "pardon Sugar", addressed=True)        # doit compter
        self.assertEqual(self._score(), 0)

    def test_les_excuses_en_rafale_ne_soldent_pas_le_carnet(self):
        """L'excuse a une horloge courte, mais elle en a une : « dsl dsl dsl » ne suffit pas."""
        self.book.update("1", "t'es nulle", addressed=True)
        self.book.book["1"]["last_aggro_ts"] = 0.0
        self.book.update("1", "ta gueule", addressed=True)
        self.book.book["1"]["last_aggro_ts"] = 0.0
        self.book.update("1", "espèce de débile", addressed=True)
        self.assertEqual(self._score(), 5)

        self.book.update("1", "dsl", addressed=True)
        self.book.update("1", "dsl", addressed=True)
        self.book.update("1", "dsl", addressed=True)
        self.assertEqual(self._score(), 3,
                         "seule la première excuse de la rafale doit compter")

    def test_le_spam_de_merci_reste_bloque(self):
        """Le garde-fou d'origine tient toujours : on ne se rachète pas en spammant."""
        self.book.update("1", "t'es nulle", addressed=True)
        for _ in range(5):
            self.book.update("1", "merci !", addressed=True)
        self.assertEqual(self._score(), 1)


if __name__ == "__main__":
    unittest.main()
