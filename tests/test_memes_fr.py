# -*- coding: utf-8 -*-
import pytest
from shared.memes_fr import pick_meme, build_meme_consigne, MEMES_FR

def test_pick_meme_no_match():
    # Aucun tag pertinent
    res = pick_meme("xyzabc non-existent word", set())
    assert res is None

def test_pick_meme_recent_refs_excluded():
    # Contexte qui matche "Macron" ("sûr")
    # Mais si "Macron" est dans recent_refs, il ne doit pas être renvoyé
    ref_macron = "le « fort sûr » de Macron (assurance excessive qui sonne faux)"
    res = pick_meme("Je suis tout à fait sûr de mon coup", {ref_macron})
    # S'il y a d'autres candidats, il peut en renvoyer un autre,
    # mais s'il renvoie qqch, ça ne doit PAS être Macron.
    if res:
        assert res["ref"] != ref_macron

def test_pick_meme_matches_tag():
    # Contexte qui contient "sûr"
    res = pick_meme("tu es sûr ?", set())
    assert res is not None
    # Il doit matcher Macron ou un autre contenant le tag "sûr"
    assert "sûr" in res["tags"]

def test_build_meme_consigne_proba_zero():
    res = build_meme_consigne("tu es sûr ?", set(), proba=0.0)
    assert res == ""

def test_build_meme_consigne_proba_one_match():
    res = build_meme_consigne("tu es sûr ?", set(), proba=1.0)
    assert "[CLIN D'ŒIL CULTUREL" in res or "[CLIN D'" in res
    assert "REFORMULANT" in res and "STYLE" in res


def test_build_meme_consigne_proba_one_no_match():
    res = build_meme_consigne("xyzabc word", set(), proba=1.0)
    assert res == ""

def test_accents_robustness():
    # Tag a un accent ("sûr"), contexte n'en a pas ("sur")
    res1 = pick_meme("tu es sur ?", set())
    assert res1 is not None
    assert any(tag in ["sûr", "certain"] for tag in res1["tags"])

    # Tag n'a pas d'accent ("biere"), contexte en a ("bière")
    res2 = pick_meme("je prends une bière", set())
    assert res2 is not None
    assert "bière" in res2["tags"] or "biere" in res2["tags"]
