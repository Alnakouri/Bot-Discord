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

from sheo_llm import build_anti_tic_consigne

def test_anti_tic_empty_or_none():
    assert build_anti_tic_consigne(None) == ""
    assert build_anti_tic_consigne([]) == ""
    assert build_anti_tic_consigne(["", None, "   "]) == ""

def test_anti_tic_extraction():
    recent = [
        "Bonjour mon cher mortel ! J'adore le fromage. 🧀",
        "<thought>Pensée</thought> Silence, ver de terre ! Haskill, apporte les cuillères. 🥄",
    ]
    consigne = build_anti_tic_consigne(recent)
    
    assert "[ANTI-TICS — VARIE OU MEURS]" in consigne
    # Amorces attendues normalisées (minuscules, sans ponctuation de bord, max 5 mots)
    # "Bonjour mon cher mortel ! J'adore le fromage." -> "bonjour mon cher mortel j'adore"
    # "Silence, ver de terre ! Haskill, apporte les cuillères." -> "silence ver de terre haskill"
    assert '"bonjour mon cher mortel j\'adore"' in consigne
    assert '"silence ver de terre haskill"' in consigne

    # Clôtures attendues (dernière phrase normalisée, max 5 mots, emoji retiré)
    # "J'adore le fromage." -> "j'adore le fromage"
    # "Haskill, apporte les cuillères." -> "haskill apporte les cuillères"
    assert '"j\'adore le fromage"' in consigne
    assert '"haskill apporte les cuillères"' in consigne

def test_anti_tic_thought_tag_ignored():
    recent = [
        "<thought>Ne dis rien</thought> Pourquoi cette question stupide ? 🥱"
    ]
    consigne = build_anti_tic_consigne(recent)
    assert '"pourquoi cette question stupide"' in consigne
