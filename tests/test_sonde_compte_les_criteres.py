# -*- coding: utf-8 -*-
"""Tests unitaires pour le comptage mécanique et l'option --relire de la sonde (SUITE 9)."""
import asyncio
import sys
from pathlib import Path
from tools.sonde_phrase_de_lien import compter, main


def test_tutoiement_et_melange_phrase_1():
    p = (
        "Combien d'épées rouillées ton forgeron a-t-il déjà pliées en deux en Bohême ? "
        "Venez nous raconter vos pires ratés sur Discord ! ✨"
    )
    res = compter([p])
    assert res["tutoiement"] == 1
    assert res["melange"] == 1
    assert res["premiers_mots"]["combien"] == 1
    assert res["questions_courtes"] == 1
    assert res["discord"] == 1


def test_tutoiement_et_melange_phrase_2():
    p = (
        "Bohemia vous a fait suer sang et eau ou juste baver sur votre écran ? "
        "Viens en débattre sur Discord. ✨"
    )
    res = compter([p])
    assert res["tutoiement"] == 1
    assert res["melange"] == 1
    assert res["premiers_mots"]["bohemia"] == 1
    assert res["discord"] == 1


def test_expression_figee_ni_tutoiement_ni_melange():
    p = (
        "Entre épées, châteaux de Bohême et boue en veux-tu en voilà, quel est votre "
        "personnage ou lieu préféré dans ce jeu ? Venez tout nous raconter sur Discord ! ✨"
    )
    res = compter([p])
    assert res["tutoiement"] == 0
    assert res["melange"] == 0
    assert res["premiers_mots"]["entre"] == 1
    assert res["discord"] == 1


def test_tutoiement_sans_melange():
    p = (
        "Combien d'heures perdues dans la boue de cette Bohême médiévale ? "
        "Viens nous raconter tes misères sur Discord ✨"
    )
    res = compter([p])
    assert res["tutoiement"] == 1
    assert res["melange"] == 0
    assert res["premiers_mots"]["combien"] == 1
    assert res["discord"] == 1


def test_redites_meme_question_et_meme_invitation_sans_emoji():
    p1 = "Combien de têtes de bandits avez-vous croisées en Bohême ? Venez en discuter sur Discord ! ✨"
    p2 = "Combien de têtes de bandits avez-vous croisées en Bohême ? Venez en discuter sur Discord ! 🍬"
    res = compter([p1, p2])
    assert res["meme_question"] == 2
    assert res["meme_invitation"] == ("venez en discuter sur discord", 2)


def test_phrase_sans_point_interrogation():
    p = "Venez nous rejoindre sur Discord sans poser de question"
    res = compter([p])
    assert res["questions_courtes"] == 0
    assert res["meme_question"] == 0
    assert res["meme_invitation"] == ("venez nous rejoindre sur discord sans poser de question", 1)


def test_premier_mot():
    p = "Entre nous, quel est votre avis ?"
    res = compter([p])
    assert res["premiers_mots"]["entre"] == 1


def test_relire_sans_charger(tmp_path: Path, monkeypatch, capsys):
    fichier = tmp_path / "sortie_test.txt"
    fichier.write_text(
        "sugar | tete=gemini | n=3\n"
        "==============================================================================\n"
        "  1. [ 1.12s] (choix) Entre l'épée et l'arc, que préférez-vous ? Venez sur Discord ! ✨\n"
        "  2. [60.00s] <<repli sur le gabarit fixe>>\n"
        "  3. [ 1.45s] Combien de fois êtes-vous mort en Bohême ? Venez nous le dire sur Discord ! ✨\n"
        "==============================================================================\n",
        encoding="utf-8",
    )

    def faux_charger(bot_id):
        raise RuntimeError("charger() ne doit PAS être appelé lors de --relire !")

    monkeypatch.setattr("tools.sonde_phrase_de_lien.charger", faux_charger)
    monkeypatch.setattr(sys, "argv", ["sonde_phrase_de_lien.py", "--relire", str(fichier)])

    code = asyncio.run(main())
    assert code == 0

    captured = capsys.readouterr().out
    assert "exploitables      : 2/3" in captured
    assert "(1 tombees sur le gabarit fixe)" in captured
    assert "type choix" in captured
    assert "1 phrase ; premier mot 1x « entre »" in captured
