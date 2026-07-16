# -*- coding: utf-8 -*-
"""Rollout du pont anti-doublon Discord↔Twitch sur Johnny + Sugar.

1. `merge_recent_responses` vit désormais dans shared/response_memory.py (fonction pure,
   copiée du pilote Sheo — sa copie sheo_llm.py reste intacte, bots indépendants).
2. Le câblage des deux bots est vérifié SUR LE SOURCE (bot_johnny.py / bot_sugar.py sont
   trop lourds à importer sous pytest — pattern de test_johnny_persona.py).
"""
import os
import sys

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.response_memory import merge_recent_responses


# ─── 1. Fonction pure partagée (mêmes cas que test_twitch_double_repetition) ───

def test_merge_recent_responses_none_safe():
    assert merge_recent_responses(None, None, limit=5) == []
    assert merge_recent_responses([], [], limit=5) == []


def test_merge_recent_responses_dedup_and_order():
    src1 = ["A", "B", "C"]
    src2 = ["B", "D"]
    assert merge_recent_responses(src1, src2, limit=3) == ["B", "C", "D"]
    assert merge_recent_responses(src1, src2, limit=10) == ["A", "B", "C", "D"]


def test_merge_recent_responses_skips_empty_entries():
    assert merge_recent_responses(["", "A", None], ["A", "B"]) == ["A", "B"]


# ─── 2. Câblage des bots (asserts sur le source) ───

def _bot_source(bot_dir, filename):
    path = os.path.join(_parent_dir, bot_dir, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _assert_pont_wiring(content, bot_label):
    # Twitch lit Discord : provider posé avant le create_task
    assert "twitch_chat.extra_recent_provider = lambda:" in content, \
        f"{bot_label}: extra_recent_provider non posé"
    # Discord lit Twitch : helper + fusion dans le bloc anti-répétition
    assert "def _twitch_recent_responses" in content, \
        f"{bot_label}: helper _twitch_recent_responses manquant"
    assert "recent_self_responses" in content, \
        f"{bot_label}: le helper ne lit pas recent_self_responses"
    assert "merge_recent_responses(" in content, \
        f"{bot_label}: fusion Discord+Twitch absente du prompt"
    assert "_twitch_recent_responses()," in content, \
        f"{bot_label}: la fusion ne reçoit pas la source Twitch"
    # Consigne renforcée « mots-clés saillants » (v2 du pont, c651489)
    assert "mot-clé saillant" in content, \
        f"{bot_label}: consigne mot-clé saillant absente"


def test_johnny_pont_wiring():
    _assert_pont_wiring(_bot_source("JohnnyBot", "bot_johnny.py"), "Johnny")


def test_sugar_pont_wiring():
    _assert_pont_wiring(_bot_source("SugarBot", "bot_sugar.py"), "Sugar")


def test_sheo_pilote_intact():
    """Garde-fou du plan : Sheo (pilote déployé/validé) n'est pas touché par le rollout."""
    content = _bot_source("Sheogorath", "bot_sheogorath.py")
    _assert_pont_wiring(content, "Sheo")
    # Sheo garde SA copie de merge_recent_responses (import depuis sheo_llm)
    assert "merge_recent_responses" in _bot_source("Sheogorath", "sheo_llm.py")
