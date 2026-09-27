# -*- coding: utf-8 -*-
"""Tests unitaires pour la sonde LAYA défaite (SUITE 10).

Vérifie la construction des requêtes et le décodage des réponses sans appeler Docker.
"""
from tools.sonde_laya_defaite import (
    construire_requete,
    lire_reponse,
    CRITERES_DEFAITE,
    INSTRUCTIONS_DEFAITE,
)


def test_construire_requete():
    replique = "Les papillons ont des plumes d'or."
    message = "les papillons n'ont pas de plume, idiot"

    req = construire_requete(replique, message)

    attendu_state = (
        "Dernière réplique du bot : « Les papillons ont des plumes d'or. »\n"
        "Message reçu en réponse : « les papillons n'ont pas de plume, idiot »"
    )
    assert req["state"] == attendu_state
    assert "questions" in req
    assert "defaite" in req["questions"]

    q = req["questions"]["defaite"]
    assert q["type"] == "choice"
    assert q["instructions"] == INSTRUCTIONS_DEFAITE
    assert q["instructions"] == "Que fait ce message face à la réplique du bot ?"
    assert q["criteria"] == CRITERES_DEFAITE
    assert (
        q["criteria"]["pris_en_defaut"]
        == "montre, par un fait ou un argument, que la réplique du bot était fausse, absurde ou se contredisait"
    )
    assert (
        q["criteria"]["victoire_proclamee"]
        == "proclame que le bot a perdu, est à court d'arguments ou se répète"
    )
    assert (
        q["criteria"]["aucune"]
        == "tout le reste : une question, une blague, une insulte sans argument, un désaccord sans preuve, du bavardage"
    )


def test_lire_reponse_factice():
    sortie_factice = {
        "answers": {
            "defaite": {
                "type": "choice",
                "choice": "aucune",
                "confidence": 0.4,
            }
        }
    }
    etiquette, confiance = lire_reponse(sortie_factice)
    assert etiquette == "aucune"
    assert confiance == 0.4


def test_lire_reponse_pris_en_defaut():
    sortie_factice = {
        "answers": {
            "defaite": {
                "type": "choice",
                "choice": "pris_en_defaut",
                "confidence": 0.88,
            }
        }
    }
    etiquette, confiance = lire_reponse(sortie_factice)
    assert etiquette == "pris_en_defaut"
    assert confiance == 0.88
