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

from sheo_llm import build_anti_tic_consigne, _strip_echo_opening

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


# --- _strip_echo_opening : tue l'ouverture-perroquet HURLÉE, épargne le reste ---

def test_echo_shouted_caps_stripped():
    # Ouverture qui HURLE l'insulte en écho → coupée, la vanne survit.
    reply = 'Oh, "FACE DE PET" ! Tes insultes sont des haïkus scatologiques, barbare des latrines ! 🎺'
    out = _strip_echo_opening(reply, "sheo la face de pet")
    assert not out.lower().startswith("oh")
    assert "haïkus scatologiques" in out

def test_echo_interjection_then_caps_stripped():
    # Interjection « Ah... » PUIS écho hurlé → les deux sautent, la morsure reste.
    reply = 'Ah... "TÊTE DE CUL"... Espèce de misérable, je te réduis en poussière ! 🔪'
    out = _strip_echo_opening(reply, "çava tete de cul ?")
    assert "misérable" in out
    assert "tête de cul" not in out.lower()

def test_normal_case_reflection_preserved():
    # Écho en casse NORMALE sur une remarque anodine (canon) → JAMAIS touché.
    reply = "Des pâtes ? Sans la moindre meule de fromage ? Quel sacrilège ! 🧀"
    assert _strip_echo_opening(reply, "j'ai mangé des pâtes") == reply

def test_all_caps_easter_egg_preserved():
    # Cri intégral en majuscules (easter egg) → JAMAIS touché.
    reply = "SILENCE, MORTEL ! LE PRINCE A PARLÉ ! 👑"
    assert _strip_echo_opening(reply, "sheo tais toi") == reply

def test_non_echo_opening_untouched():
    # Ouverture qui n'échote pas le mortel → intacte.
    reply = "Quelle audace délicieuse ! Haskill, apporte la laitue. 🥬"
    assert _strip_echo_opening(reply, "tu es nul") == reply

def test_empty_inputs():
    assert _strip_echo_opening("", "insulte") == ""
    assert _strip_echo_opening("Une réponse.", "") == "Une réponse."
