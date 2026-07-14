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
