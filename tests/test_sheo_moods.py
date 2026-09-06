# -*- coding: utf-8 -*-
import os
import sys
import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_sheo_dir = os.path.join(_parent_dir, "Sheogorath")
if _sheo_dir not in sys.path:
    sys.path.insert(0, _sheo_dir)

import sheo_data

def test_sheo_moods_exist_and_contain_placeholder():
    assert "neutral" in sheo_data.MOOD_PROMPTS
    assert "mania" in sheo_data.MOOD_PROMPTS
    assert "dementia" in sheo_data.MOOD_PROMPTS
    assert "bliss" in sheo_data.MOOD_PROMPTS
    
    for mood, prompt in sheo_data.MOOD_PROMPTS.items():
        assert "{comebacks_placeholder}" in prompt, f"Mood {mood} prompt is missing the comebacks placeholder"

def test_sheo_moods_are_distinct():
    neutral = sheo_data.MOOD_PROMPTS["neutral"]
    mania = sheo_data.MOOD_PROMPTS["mania"]
    dementia = sheo_data.MOOD_PROMPTS["dementia"]
    bliss = sheo_data.MOOD_PROMPTS["bliss"]
    
    assert neutral != mania
    assert neutral != dementia
    assert neutral != bliss
    assert mania != dementia
    assert mania != bliss
    assert dementia != bliss
    
    # Check that they contain distinct comedy examples
    assert "[EXEMPLES DE RÉPARTIE (HUMEUR : NEUTRE)]" in neutral
    assert "[EXEMPLES DE RÉPARTIE (HUMEUR : MANIA)]" in mania
    assert "[EXEMPLES DE RÉPARTIE (HUMEUR : DEMENTIA)]" in dementia
    assert "[EXEMPLES DE RÉPARTIE (HUMEUR : BLISS)]" in bliss

import sheo_llm

def test_no_tts_brackets_in_fewshot():
    for name in ["COMEDY_EXAMPLES_NEUTRAL", "COMEDY_EXAMPLES_MANIA", "COMEDY_EXAMPLES_DEMENTIA", "COMEDY_EXAMPLES_BLISS"]:
        val = getattr(sheo_data, name)
        for tag in ["[laugh]", "[chuckle]", "[sigh]", "[shout]"]:
            assert tag not in val.lower(), f"{name} contains forbidden TTS tag {tag}"

def test_clean_strips_tts_tags():
    input_text = "Haha ! [laugh] Voyez ça [sigh]"
    cleaned = sheo_llm.clean_internal_tags(input_text)
    assert "[laugh]" not in cleaned
    assert "[sigh]" not in cleaned
    assert cleaned == "Haha ! Voyez ça"

import re
from shared.twitch.sanitize import strip_stage_directions

def test_sheo_tutoie():
    for trigger, reply in sheo_data.COMEBACK_POOL:
        assert not re.search(r"\b(vous|votre)\b", reply, re.IGNORECASE), f"COMEBACK_POOL reply contains vous/votre: {reply}"
    
    for name in ["COMEDY_EXAMPLES_NEUTRAL", "COMEDY_EXAMPLES_MANIA", "COMEDY_EXAMPLES_DEMENTIA", "COMEDY_EXAMPLES_BLISS"]:
        val = getattr(sheo_data, name)
        assert not re.search(r"\b(vous|votre)\b", val, re.IGNORECASE), f"{name} contains vous/votre: {val}"

def test_strip_prose_stage_directions():
    text1 = "Haha ! <Un silence. Puis un chuchotement rauque...> Tu as peur ?"
    cleaned1 = strip_stage_directions(text1)
    assert cleaned1 == "Haha ! Tu as peur ?"
    
    text2 = "Non ! un soupir théâtral C'est faux."
    cleaned2 = strip_stage_directions(text2)
    assert cleaned2 == "Non ! C'est faux."
    
    text3 = "Viens voir <@1234567890> ! C'est le boss."
    cleaned3 = strip_stage_directions(text3)
    assert cleaned3 == "Viens voir <@1234567890> ! C'est le boss."


def test_writing_rendering_prompts():
    # Verify PERSONALITY_BASE contains the RENDU ÉCRIT DE TON ÉTAT block
    assert "RENDU ÉCRIT DE TON ÉTAT" in sheo_data.PERSONALITY_BASE
    
    # Verify NEUTRAL, MANIA, DEMENTIA, BLISS mood prompts contain their respective instructions
    neutral = sheo_data.MOOD_PROMPTS["neutral"]
    mania = sheo_data.MOOD_PROMPTS["mania"]
    dementia = sheo_data.MOOD_PROMPTS["dementia"]
    bliss = sheo_data.MOOD_PROMPTS["bliss"]
    
    assert "casse NORMALE" in neutral
    assert "calme glacial" in neutral
    
    assert "tu es BRUYANT" in mania
    assert "MAJUSCULES giclent" in mania
    
    assert "tu CHUCHOTES" in dementia
    assert "AUCUN cri" in dementia
    assert "AUCUNE majuscule" in dementia

    assert "FOU JOVIAL & LUCIDE" in bliss
    assert "casse normale et chaleureuse" in bliss


def test_sheo_new_behaviors():
    # Verify PERSONALITY_BASE is included in PERSONALITY_BLISS
    assert sheo_data.PERSONALITY_BASE in sheo_data.PERSONALITY_BLISS
    
    # Verify transversal blocks Phase A (double-sens) and Phase B (conteur) are in PERSONALITY_BASE
    assert "CAPRICE À DOUBLE SENS" in sheo_data.PERSONALITY_BASE
    assert "EXCEPTION DU CONTEUR" in sheo_data.PERSONALITY_BASE
    
    # Verify they are therefore in all 4 moods
    for mood, prompt in sheo_data.MOOD_PROMPTS.items():
        assert "CAPRICE À DOUBLE SENS" in prompt, f"Mood {mood} prompt is missing Phase A block"
        assert "EXCEPTION DU CONTEUR" in prompt, f"Mood {mood} prompt is missing Phase B block"


def test_sheo_length_rules():
    assert "QUI DÉCIDE DE LA LONGUEUR" in sheo_data.PERSONALITY_BASE
    assert "jamais en défense" in sheo_data.PERSONALITY_BASE
    assert "4 MAXIMUM" in sheo_data.PERSONALITY_BASE
    assert "INVITE EXPLICITEMENT" in sheo_data.PERSONALITY_BASE




# ---------------------------------------------------------------------------
# Les enveloppes vides : chaque nettoyeur retire un contenu, aucun ne ramassait
# le delimiteur devenu vide
# ---------------------------------------------------------------------------

def test_une_enveloppe_videe_de_son_contenu_disparait_aussi():
    """⚠️ Constate en live le 2026-09-06, message `!neutre` de LeDev.

    La reponse de Sheo se terminait par « ...lors de ta prochaine crise de rage ? 🎩 () »
    — la parenthese vide est bien en base, ce n'est pas un artefact d'affichage.

    Le mecanisme est generique : `clean_internal_tags` retire `[laugh]`,
    `strip_markdown_emphasis` retire `*rire*`, l'extracteur de faits retire
    `<fact>...</fact>`. Aucun ne regarde le delimiteur qui les entourait.
    """
    from sheo_llm import clean_internal_tags

    assert clean_internal_tags("Va compter les dents. 🎩 ([laugh])").endswith("🎩")
    assert "()" not in clean_internal_tags("Haskill ! ([laugh]) Apporte le the.")
    assert "[]" not in clean_internal_tags("Un ordre [<fact>x</fact>] et puis rien.")


def test_une_enveloppe_qui_contient_encore_quelque_chose_est_intacte():
    """Le nettoyage ne doit pas manger une vraie parenthese : `(vraiment)` reste."""
    from sheo_llm import clean_internal_tags

    sortie = clean_internal_tags("Un cornichon (vraiment) chantant.")
    assert "(vraiment)" in sortie
