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
    
    for mood, prompt in sheo_data.MOOD_PROMPTS.items():
        assert "{comebacks_placeholder}" in prompt, f"Mood {mood} prompt is missing the comebacks placeholder"

def test_sheo_moods_are_distinct():
    neutral = sheo_data.MOOD_PROMPTS["neutral"]
    mania = sheo_data.MOOD_PROMPTS["mania"]
    dementia = sheo_data.MOOD_PROMPTS["dementia"]
    
    assert neutral != mania
    assert neutral != dementia
    assert mania != dementia
    
    # Check that they contain distinct comedy examples
    assert "[EXEMPLES DE RÉPARTIE (HUMEUR : NEUTRE)]" in neutral
    assert "[EXEMPLES DE RÉPARTIE (HUMEUR : MANIA)]" in mania
    assert "[EXEMPLES DE RÉPARTIE (HUMEUR : DEMENTIA)]" in dementia

import sheo_llm

def test_no_tts_brackets_in_fewshot():
    for name in ["COMEDY_EXAMPLES_NEUTRAL", "COMEDY_EXAMPLES_MANIA", "COMEDY_EXAMPLES_DEMENTIA"]:
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
    
    for name in ["COMEDY_EXAMPLES_NEUTRAL", "COMEDY_EXAMPLES_MANIA", "COMEDY_EXAMPLES_DEMENTIA"]:
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
