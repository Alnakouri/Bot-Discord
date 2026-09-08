# -*- coding: utf-8 -*-
"""Le helper OAuth doit dire QUEL COMPTE connecter.

⚠️ Le seul echec probable de la manip EventSub est de se connecter avec le compte du
BOT au lieu de celui du STREAMER : le token rendu n'est proprietaire d'aucune chaine, et
les 7 abonnements « channel.… » repondent 403. Le script affichait sa consigne « COMPTE
DU BOT » meme lance avec le suffixe `_broadcaster` : l'outil dictait lui-meme la faute.

Second piege : le bloc « a ajouter dans le .env » proposait de coller le token du
streamer dans TWITCH_OAUTH_TOKEN — le bot aurait alors parle SOUS L'IDENTITE du streamer
dans son propre chat.

⚠️ Un test qui cherche le NOM d'un helper passe au vert sur un simple import
([[gotcha-import-ajoute-mais-pas-cable]]) : on exige donc l'APPEL dans `main`, et
l'ABSENCE du code remplace.
"""
import ast
import os
import sys
import unittest
from pathlib import Path

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import twitch_authorize

SOURCE = Path(_parent_dir) / "twitch_authorize.py"


class TestConsigneCompte(unittest.TestCase):
    def test_bot_ordinaire_demande_le_compte_du_bot(self):
        texte = twitch_authorize.consigne_compte("sheogorath")
        self.assertIn("COMPTE DU BOT", texte)
        self.assertNotIn("STREAMER", texte)

    def test_suffixe_broadcaster_demande_le_compte_du_streamer(self):
        texte = twitch_authorize.consigne_compte("sheogorath_broadcaster")
        self.assertIn("COMPTE DU STREAMER", texte)
        # La consigne doit aussi dire ce qu'il ne faut PAS faire.
        self.assertIn("PAS avec le compte du bot", texte)


class TestLignesEnv(unittest.TestCase):
    def test_bot_ordinaire_donne_les_deux_lignes(self):
        texte = twitch_authorize.lignes_env("sheogorath", "ACCESS", "REFRESH")
        self.assertIn("TWITCH_OAUTH_TOKEN=ACCESS", texte)
        self.assertIn("TWITCH_REFRESH_TOKEN=REFRESH", texte)

    def test_broadcaster_ne_propose_JAMAIS_de_coller_le_token(self):
        texte = twitch_authorize.lignes_env("sheogorath_broadcaster", "ACCESS", "REFRESH")
        self.assertNotIn("TWITCH_OAUTH_TOKEN=", texte)
        self.assertNotIn("ACCESS", texte)
        self.assertNotIn("REFRESH", texte)
        self.assertIn("NE recopie PAS", texte)

    def test_rien_d_imprime_ne_casse_une_console_cp1252(self):
        # Le script tourne dans un terminal Windows : un emoji dans un texte IMPRIME
        # leverait UnicodeEncodeError au tout dernier pas de la manip.
        for bot in ("sheogorath", "sheogorath_broadcaster"):
            for texte in (twitch_authorize.consigne_compte(bot),
                          twitch_authorize.lignes_env(bot, "A", "B")):
                texte.encode("cp1252")


class TestCablage(unittest.TestCase):
    """Les helpers existent : encore faut-il que `main` les APPELLE."""

    def setUp(self):
        arbre = ast.parse(SOURCE.read_text(encoding="utf-8"))
        self.main = next(n for n in arbre.body
                         if isinstance(n, ast.FunctionDef) and n.name == "main")
        self.appels = {n.func.id for n in ast.walk(self.main)
                       if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}

    def test_main_appelle_les_deux_helpers(self):
        self.assertIn("consigne_compte", self.appels)
        self.assertIn("lignes_env", self.appels)

    def test_le_code_remplace_a_bien_disparu(self):
        # L'ancienne consigne en dur et l'ancien bloc .env ne doivent plus etre imprimes.
        litteraux = {n.value for n in ast.walk(self.main)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        for litteral in litteraux:
            self.assertNotIn("COMPTE DU BOT", litteral)
            self.assertNotIn("TWITCH_OAUTH_TOKEN=", litteral)


if __name__ == "__main__":
    unittest.main()
