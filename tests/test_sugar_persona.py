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
