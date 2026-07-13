# -*- coding: utf-8 -*-
"""Non-régression : deux bugs exposés par le test live 2026-07-14 (réponses plus longues).
1. Une balise <fact> TRONQUÉE (ouvrante sans </fact>, coupée par le plafond de tokens) faisait
   FUIR le fait interne en clair dans le message.
2. Le plafond de tokens coupait la réponse EN PLEIN MOT (« ...Un from »)."""
import os
import sys

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_sheo_dir = os.path.join(_parent_dir, "Sheogorath")
if _sheo_dir not in sys.path:
    sys.path.insert(0, _sheo_dir)

from sheo_llm import extract_facts, _trim_incomplete_tail


class _FakeBrain:
    def __init__(self):
        self.stored = []

    def add_fact(self, user_id, fact):
        self.stored.append(fact)


def test_fact_complet_stocke_et_retire():
    fb = _FakeBrain()
    out = extract_facts("Bonjour mortel. <fact>Aime le fromage</fact>", fb, 1)
    assert out == "Bonjour mortel."
    assert fb.stored == ["Aime le fromage"]


def test_fact_tronque_ne_fuit_pas_et_non_stocke():
    fb = _FakeBrain()
    leaked = ("Tu veux diriger la répétition ? 🎼 <fact>L'utilisateur semble attaché aux "
              "insultes et révélant une fixation sur le bas corpor")
    out = extract_facts(leaked, fb, 1)
    assert "utilisateur semble" not in out
    assert out.endswith("🎼")
    assert fb.stored == []  # fait incomplet → pas enregistré


def test_sans_fact_texte_intact():
    fb = _FakeBrain()
    out = extract_facts("Juste une réponse normale, mortel.", fb, 1)
    assert out == "Juste une réponse normale, mortel."
    assert fb.stored == []


def test_trim_coupe_en_plein_mot():
    assert _trim_incomplete_tail("Une chaise ? Un pot de chambre ? Un from") == "Une chaise ? Un pot de chambre ?"


def test_trim_preserve_fin_propre():
    # Emoji de ton final
    assert _trim_incomplete_tail("Tu veux essayer ? 🎻") == "Tu veux essayer ? 🎻"
    # Ponctuation terminale
    assert _trim_incomplete_tail("Silence, mortel !") == "Silence, mortel !"
    # Tiret d'auto-interruption VOULU (didascalie vocale de la persona)
    assert _trim_incomplete_tail("Prépare-toi, mortel —") == "Prépare-toi, mortel —"


def test_trim_ne_casse_pas_sans_phrase_complete():
    # Aucune ponctuation de fin nulle part → on ne casse rien.
    assert _trim_incomplete_tail("juste un fragment sans ponctuation") == "juste un fragment sans ponctuation"
