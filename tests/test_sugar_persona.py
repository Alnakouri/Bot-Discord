# -*- coding: utf-8 -*-
import os
import sys
import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_sugar_dir = os.path.join(_parent_dir, "SugarBot")
if _sugar_dir not in sys.path:
    sys.path.insert(0, _sugar_dir)

import sugar_data

def test_sugar_personality_prompt_gender_agreement():
    prompt = sugar_data.PERSONALITY_PROMPT
    
    # 1. L'accord : PERSONALITY_PROMPT contient « péteur », jamais au hasard et ne contient plus choisis au hasard
    assert "« péteur », jamais au hasard" in prompt
    assert "choisis au hasard" not in prompt
    
    # Check that "péteur (ou péteuse si c'est une femme — accord obligatoire)" is in prompt
    assert "péteur (ou péteuse si c'est une femme — accord obligatoire)" in prompt

def test_sugar_personality_prompt_twitch_streamer():
    prompt = sugar_data.PERSONALITY_PROMPT
    
    # 2. La streameuse : PERSONALITY_PROMPT contient ma_streameuse, twitch.tv/ma_streameuse et la consigne anti-ping
    assert "ma_streameuse" in prompt
    assert "twitch.tv/ma_streameuse" in prompt
    assert "JAMAIS son nom avec un @" in prompt


# ---------------------------------------------------------------------------------------
# Le budget de mots : sa fiche dit « ~30 mots, JAMAIS plus »
# ---------------------------------------------------------------------------------------

def test_sugar_tient_son_budget_de_30_mots():
    """⚠️ Mesure sur les 85 reponses des rapports d'eval du 16 au 19/09 : **18 depassaient
    30 mots**, jusqu'a 67. Sa fiche dit pourtant « Vise ~30 mots, JAMAIS plus »
    (`sugar_data.py:30`), et le harnais le mesure deja (`deterministic.py`, cas
    `sugar_30_mots`) — il sortait `False` a chaque passe.
    """
    from SugarBot.sugar_filtres import filtre_sortie

    trop_long = (
        "La vie, c'est un bonbon a croquer sans se presser : on savoure l'enveloppe "
        "avant de decouvrir le coeur. Et le mien ? C'est un melange de sang-froid et "
        "de rires qui grattent les nerfs des peteurs. Si tu veux des details, je te "
        "conseille d'aller voir ailleurs, elle explique bien mieux que moi."
    )
    assert len(trop_long.split()) > 30, "le cas de test ne teste rien"
    rendu = filtre_sortie(trop_long)
    assert len(rendu.split()) <= 30, f"{len(rendu.split())} mots rendus"


def test_le_budget_ne_coupe_JAMAIS_au_milieu_d_une_phrase():
    """⚠️ Une punchline amputee est pire qu'une punchline longue.

    Le filet garde des phrases ENTIERES, et jamais moins d'une — meme si cette seule
    phrase depasse le budget. Trois des 85 reponses mesurees sont dans ce cas (max 34
    mots) : les raccourcir voudrait dire couper dedans, et « ~30 » est approximatif.
    """
    from SugarBot.sugar_filtres import budget_de_mots

    une_seule = ("Un serpentard ne balance jamais ses petits secrets comme on jette des "
                 "bonbons a la fete foraine, surtout quand on le lui demande aussi "
                 "maladroitement que tu viens de le faire devant tout le monde.")
    assert len(une_seule.split()) > 30, "le cas de test ne teste rien"
    assert budget_de_mots(une_seule) == une_seule, (
        "Le filet a coupe dans une phrase unique au lieu de la laisser passer."
    )

    deux = "Premiere phrase courte. " + " ".join(["mot"] * 40) + "."
    rendu = budget_de_mots(deux)
    assert rendu == "Premiere phrase courte.", (
        "La deuxieme phrase ne tenait pas dans le budget : elle devait tomber ENTIERE."
    )


def test_le_budget_epargne_une_reponse_deja_courte_et_est_idempotent():
    """Un filet qui rogne le nominal n'est plus un filet. Et sur Discord, le tour suivant
    relit le message DEJA envoye
    ([[gotcha-un-filtre-non-idempotent-laisse-du-travail-a-l-ecran]])."""
    from SugarBot.sugar_filtres import filtre_sortie

    courte = "Quel peteur ambitieux. Tes secrets sont plus mal gardes que les miens."
    assert filtre_sortie(courte) == courte

    long_texte = " ".join("Phrase numero %d ici meme." % i for i in range(1, 12))
    une_fois = filtre_sortie(long_texte)
    assert filtre_sortie(une_fois) == une_fois


def test_le_budget_preserve_l_emoji_final_et_ne_le_compte_pas():
    """L'emoji de ton ferme la replique ; le perdre en tronquant change le ton."""
    from SugarBot.sugar_filtres import budget_de_mots

    texte = ("Les critiques, c'est comme les bonbons aigres : ca pique la langue et ca "
             "passe mal. Mais un vrai peteur en fait un sport national, et ca c'est "
             "juste pathetique de sa part. \U0001F36C")
    rendu = budget_de_mots(texte)
    assert rendu.endswith("\U0001F36C"), "l'emoji de ton a disparu"
    # L'emoji ne doit pas manger une place dans le budget.
    assert len(rendu.replace("\U0001F36C", "").split()) <= 30
