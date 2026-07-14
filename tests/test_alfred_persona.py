# -*- coding: utf-8 -*-
import os
import sys
import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_alfred_dir = os.path.join(_parent_dir, "Alfred")
if _alfred_dir not in sys.path:
    sys.path.insert(0, _alfred_dir)

import alfred_data

def test_alfred_personality_prompt_contains_pillars():
    prompt = alfred_data.PERSONALITY_PROMPT
    assert "SOLLICITUDE DÉGUISÉE" in prompt
    assert "LANGUE MATERNELLE" in prompt
    
    # Old rule should be removed
    assert "NE SOIS JAMAIS AGRÉABLE" not in prompt

def test_alfred_no_black_or_wayne_references():
    prompt = alfred_data.PERSONALITY_PROMPT
    
    assert "Maître Black" not in prompt
    assert "Résidence Black" not in prompt
    assert "Maître Wayne" not in prompt
