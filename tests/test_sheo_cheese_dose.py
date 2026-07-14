# -*- coding: utf-8 -*-
import os
import sys
import pytest
import random

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_sheo_dir = os.path.join(_parent_dir, "Sheogorath")
if _sheo_dir not in sys.path:
    sys.path.insert(0, _sheo_dir)

import sheo_data
import bot_sheogorath

def test_sheo_cheese_dose():
    # Count of "fromage" (case insensitive) in PERSONALITY_BASE
    count = sheo_data.PERSONALITY_BASE.lower().count("fromage")
    assert count <= 7, f"Count of 'fromage' in PERSONALITY_BASE is {count}, expected <= 7"
    
    # "DOSE DU FROMAGE" in PERSONALITY_BASE
    assert "DOSE DU FROMAGE" in sheo_data.PERSONALITY_BASE

def test_get_smart_string_response_knowledge_randomization():
    responses = []
    for _ in range(100):
        res = bot_sheogorath.get_smart_string_response("sais-tu un truc ?", "test_guild")
        responses.append(res)
        
    facts_count = sum(1 for r in responses if r in sheo_data.SHEO_BRAIN["cheese_facts"])
    madness_count = sum(1 for r in responses if r in sheo_data.SHEO_BRAIN["madness"])
    philosophy_count = sum(1 for r in responses if r in sheo_data.SHEO_BRAIN["philosophy"])
    
    assert facts_count > 0, "No cheese_facts response was returned"
    assert madness_count > 0, "No madness response was returned"
    assert philosophy_count > 0, "No philosophy response was returned"
