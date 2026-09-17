# -*- coding: utf-8 -*-
"""Verrou : Malena ne doit pas répondre à un message d'il y a deux heures.

Constaté en live le 2026-09-17 à 16:32. L'utilisateur écrit « j'été avec tony on fait la
paix ? » et elle répond « BÉBÉ KADOM ?? Tu recommences avec sa ? » — une insulte qu'il
avait écrite à 14:43, et à laquelle elle avait DÉJÀ répondu. Retrouvée dans
`data/malena_memory.json`, entrées 7 et 9.

Le bloc `[CONVERSATION RÉCENTE]` fermait le prompt, sans heure et sans les réponses de
Malena : le modèle lisait une rafale de messages entrants dont le dernier était une
insulte, et répondait à celui-là. Aucun test ne le voyait, et le juge de l'éval note
`anti_contamination` à 5.00 — il ne regarde pas cette question.

`DATA_DIR` est déjà isolé par `tests/conftest.py` : ces tests n'écrivent jamais dans la
mémoire des bots en service.
"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)
_MALENA = os.path.join(RACINE, "MalenaBot")
if _MALENA not in sys.path:
    sys.path.insert(0, _MALENA)

from malena_memory import MalenaMemory


def _memoire_avec_deux_membres():
    m = MalenaMemory()
    m.memory["users"] = {}
    m.memory["conversations"] = []
    m.add_interaction(1, "LeDev", "bebe kadom va", "Ferme ta bouche !")
    m.add_interaction(1, "LeDev", "tony est comme toi c'est un bebe kadom", "PARDON ??")
    m.add_interaction(2, "AutreMembre", "salut malena", "Wesh toi !")
    return m


def test_les_echanges_passes_sont_dates():
    """Sans heure, rien ne distingue une insulte d'il y a deux heures de celle de maintenant."""
    contexte = _memoire_avec_deux_membres().get_context_summary(1)
    assert "kadom" in contexte, "le contexte doit bien contenir les échanges précédents"
    assert ":" in contexte and "(" in contexte, "les échanges passés doivent porter leur heure"
    assert "PASSÉS" in contexte.upper() or "PASSES" in contexte.upper(), (
        "le bloc doit se dire PASSÉ : c'est ce que le modèle lit pour ne pas y répondre"
    )


def test_les_reponses_de_malena_figurent_dans_le_contexte():
    """Sans ses propres réponses, la suite ressemble à des messages restés SANS réponse —
    donc à des insultes encore ouvertes."""
    contexte = _memoire_avec_deux_membres().get_context_summary(1)
    assert "Ferme ta bouche" in contexte and "PARDON" in contexte, (
        "les réponses déjà faites par Malena doivent apparaître : c'est ce qui montre "
        "que l'échange est CLOS"
    )


def test_le_contexte_ne_melange_pas_deux_membres():
    """`conversations` est une liste globale : sans filtre, le contexte d'un membre
    remontait dans la réponse faite à un autre."""
    m = _memoire_avec_deux_membres()
    assert "salut malena" not in m.get_context_summary(1)
    assert "kadom" not in m.get_context_summary(2)


def test_le_message_courant_est_le_DERNIER_du_prompt():
    """⚠️ Le correctif est l'ORDRE, pas l'étiquette.

    Tant que les échanges passés fermaient le prompt, le modèle répondait au dernier
    message qu'il avait lu. L'étiquette « MESSAGE ACTUEL » ne sert à rien si le bloc de
    contexte revient derrière elle.
    """
    chemin = os.path.join(_MALENA, "bot_malena.py")
    with open(chemin, encoding="utf-8") as f:
        src = f.read()

    # Bornes tolérantes : on veut que ce test survive à une réécriture du prompt et
    # échoue sur le FOND — l'ordre — pas sur la disparition d'un littéral.
    fin = src.index("# GÉNÉRATION ROUTÉE")
    debut = src.rindex("prompt = ", 0, fin)
    bloc = src[debut:fin]

    assert "memory_context" in bloc, (
        "le contexte passé n'est plus injecté dans le prompt de Malena"
    )
    position_contexte = bloc.index("memory_context")
    position_message = bloc.index("te dit")
    assert position_contexte < position_message, (
        "le contexte passé doit être placé AVANT le message courant dans le prompt : "
        "sinon le modèle répond de nouveau au dernier message qu'il a lu"
    )
    assert "MESSAGE ACTUEL" in bloc, "le message courant doit être annoncé comme tel"
