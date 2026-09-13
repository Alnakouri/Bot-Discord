# -*- coding: utf-8 -*-
import os
import sys
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
    """Le pool du savoir tire entre cheese_facts / madness / philosophy.

    Deux pieges scelles ici :
    - l'entree doit REELLEMENT atteindre cette branche. « sais-tu » (avec le trait
      d'union) ne contient pas le mot-cle « sais tu » : le test tombait dans la
      branche par defaut, ou cheese_facts n'a que 5 % de chance de sortir — d'ou
      un echec aleatoire d'environ une execution sur 170.
    - le tirage est seme, donc la suite ne depend plus d'un coup de des.
    """
    savoir = (set(sheo_data.SHEO_BRAIN["cheese_facts"])
              | set(sheo_data.SHEO_BRAIN["madness"])
              | set(sheo_data.SHEO_BRAIN["philosophy"]))

    etat = random.getstate()
    try:
        random.seed(20260913)
        responses = [
            bot_sheogorath.get_smart_string_response("sais tu un truc ?", "test_guild")
            for _ in range(100)
        ]
    finally:
        random.setstate(etat)

    # Garde de branche : une reponse hors de ces trois pools (un « insult », par
    # exemple) signifie que l'entree n'atteint plus la branche du savoir.
    intrus = [r for r in responses if r not in savoir]
    assert not intrus, f"branche du savoir non atteinte, reponse hors pool : {intrus[0]!r}"

    facts_count = sum(1 for r in responses if r in sheo_data.SHEO_BRAIN["cheese_facts"])
    madness_count = sum(1 for r in responses if r in sheo_data.SHEO_BRAIN["madness"])
    philosophy_count = sum(1 for r in responses if r in sheo_data.SHEO_BRAIN["philosophy"])

    assert facts_count > 0, "No cheese_facts response was returned"
    assert madness_count > 0, "No madness response was returned"
    assert philosophy_count > 0, "No philosophy response was returned"
