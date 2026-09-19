# -*- coding: utf-8 -*-
import os
import sys
import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_johnny_dir = os.path.join(_parent_dir, "JohnnyBot")
if _johnny_dir not in sys.path:
    sys.path.insert(0, _johnny_dir)

import johnny_data

def test_johnny_personality_prompt_contains_pillars():
    prompt = johnny_data.PERSONALITY_PROMPT
    assert "SARCASME & IRONIE NOIRE" in prompt
    assert "TON EGO" in prompt
    assert "ALT CUNNINGHAM" in prompt
    assert "LONGUEUR = PERTINENCE" in prompt
    
    # 1-3 phrases maximum constraint must be removed
    assert "1-3 phrases maximum" not in prompt

def test_johnny_diplomatic_tales_lore():
    # Check that "Aldecaldos" is present and "l'Aldecaldo" is not
    aldecados_found = False
    for tale in johnny_data.DIPLOMATIC_TALES:
        if "Aldecaldos" in tale:
            aldecados_found = True
        assert "l'Aldecaldo" not in tale, f"Found deprecated lore term 'l'Aldecaldo' in: {tale}"
    
    assert aldecados_found, "Could not find 'Aldecaldos' in DIPLOMATIC_TALES"

def test_johnny_twitch_parity():
    # Read bot_johnny.py and check for system_prompt_provider
    bot_path = os.path.join(_johnny_dir, "bot_johnny.py")
    with open(bot_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert "system_prompt_provider=lambda: PERSONALITY_PROMPT" in content


# ---------------------------------------------------------------------------------------
# Le plafond de phrases : un filet, pas un outil de mise en forme
# ---------------------------------------------------------------------------------------

def _compte_phrases(texte):
    """Compte les VRAIES phrases, en ignorant l'emoji final recolle par le filet."""
    import re
    sans_emoji = re.sub(r"\s*[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]+\s*$", "", texte)
    protege = re.sub(r"\.\.\.+|…", "\x01", sans_emoji)
    return len([s for s in re.split(r"(?<=[.!?])\s+", protege.strip()) if s.strip()])


def test_johnny_ne_depasse_plus_son_propre_plafond():
    """⚠️ Johnny rendait 8 a 10 phrases quand sa regle en autorise 3.

    Trois interventions sur le MODELE n'y avaient rien change : ministral-14b, gpt-oss et
    flash-lite rendent tous 8-10 phrases a prompt identique (0.20 d'ecart sur un run de
    10 scenarios, soit du bruit). Ce n'est donc pas un defaut de modele, et une regle de
    prompt ne protege que ce qu'un modele veut bien suivre : d'ou ce filet.
    """
    from JohnnyBot.johnny_filtres import filtre_sortie

    dix = " ".join("Phrase numero %d." % i for i in range(1, 11))
    assert _compte_phrases(filtre_sortie(dix, "salut")) == 6

    # ⚠️ Le defaut live de Sheogorath du 2026-07-15 : un modele separe souvent ses
    # phrases par un SAUT DE LIGNE. Avec ' +' au lieu de r'\s+', elles ne sont pas
    # comptees et le filet ne se declenche JAMAIS.
    sauts = "\n".join("Ligne %d." % i for i in range(1, 11))
    assert _compte_phrases(filtre_sortie(sauts, "salut")) == 6, (
        "Les phrases separees par un saut de ligne echappent au plafond."
    )


def test_le_plafond_s_ouvre_quand_le_choom_demande_a_developper():
    """⚠️ Sans ce cas, le filet punit la ou la fiche AUTORISE.

    C'est exactement ce qui avait fait tomber la note `longueur` a 0.50/5 quand
    l'utilisateur disait « raconte »
    ([[gotcha-le-juge-punissait-la-ou-la-fiche-autorise]]).
    """
    from JohnnyBot.johnny_filtres import filtre_sortie, budget_de_phrases

    assert budget_de_phrases("salut") == 6
    assert budget_de_phrases("raconte-moi Arasaka") == 10
    assert budget_de_phrases("explique ton run") == 10

    dix = " ".join("Phrase numero %d." % i for i in range(1, 11))
    assert _compte_phrases(filtre_sortie(dix, "raconte-moi ton run")) == 10


def test_le_plafond_ne_touche_PAS_une_reponse_deja_courte():
    """Un filet qui rogne le nominal n'est plus un filet. Et il doit etre IDEMPOTENT :
    sur Discord, le tour suivant relit le message DEJA envoye
    ([[gotcha-un-filtre-non-idempotent-laisse-du-travail-a-l-ecran]])."""
    from JohnnyBot.johnny_filtres import filtre_sortie

    courte = "Et toi t'es qu'un pseudo avec un avatar. On a tous nos protheses, choom."
    assert filtre_sortie(courte, "salut") == courte

    dix = " ".join("Phrase numero %d." % i for i in range(1, 11))
    une_fois = filtre_sortie(dix, "salut")
    assert filtre_sortie(une_fois, "salut") == une_fois

    # L'emoji de ton final survit a la troncature.
    avec_emoji = " ".join("Coup %d." % i for i in range(1, 9)) + " \U0001F3B8"
    assert filtre_sortie(avec_emoji, "salut").endswith("\U0001F3B8")


def test_le_bot_passe_le_VRAI_message_du_choom_au_filtre():
    """⚠️ Le filet est inerte si l'appelant ne lui donne pas le message.

    Et ce doit etre `user_msg_content`, pas `user_message` : ce dernier a recu les
    suffixes [VISION] / [VOCAL] ajoutes par le code, dont un « Decris ce que tu vois »
    qui ouvrirait le plafond long sur un message qui ne demandait rien.

    Verrou AST sur le fichier du bot, jamais une reconstitution
    ([[gotcha-test-qui-retape-la-logique]]).
    """
    import ast
    import os

    chemin = os.path.join(_parent_dir, "JohnnyBot", "bot_johnny.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read(), filename="bot_johnny.py")

    appels = [n for n in ast.walk(arbre)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "filtre_sortie"]
    assert appels, "bot_johnny.py n'appelle plus filtre_sortie"

    nus = [n.lineno for n in appels if len(n.args) < 2]
    assert not nus, (
        f"filtre_sortie appele sans le message du choom ligne(s) {nus} : "
        "le plafond de phrases ne peut plus voir un « raconte »."
    )
    mauvais = [n.lineno for n in appels
               if isinstance(n.args[1], ast.Name) and n.args[1].id != "user_msg_content"]
    assert not mauvais, (
        f"ligne(s) {mauvais} : passer `user_message` donne au filtre un texte que le "
        "CODE a modifie ([VISION]/[VOCAL]), pas ce que le choom a ecrit."
    )
