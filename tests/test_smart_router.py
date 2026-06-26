# -*- coding: utf-8 -*-
"""Tests unitaires du routage IA (shared/smart_router.py).

Couvre la classification (texte/raisonnement/humour/image/audio/vocal) et la
cascade de modèles. Fonctions pures, aucun réseau."""
import os
import sys
import unittest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.smart_router import (
    classify_request, get_model_cascade, RequestType,
    _needs_reasoning, _needs_humor,
)


class _FakeAttachment:
    """Imite discord.Attachment pour les besoins de classify_request."""
    def __init__(self, content_type=None, filename="", is_voice_message=False, size=1024, url="http://x"):
        self.content_type = content_type
        self.filename = filename
        self.is_voice_message = is_voice_message
        self.size = size
        self.url = url


class TestClassifyRequest(unittest.TestCase):
    def test_plain_text_is_text(self):
        r = classify_request("salut, ça va ?")
        self.assertEqual(r["type"], RequestType.TEXT)
        self.assertFalse(r["has_image"])
        self.assertFalse(r["has_audio"])

    def test_empty_message_is_text(self):
        self.assertEqual(classify_request("")["type"], RequestType.TEXT)
        self.assertEqual(classify_request(None)["type"], RequestType.TEXT)

    def test_two_reasoning_keywords_trigger_reasoning(self):
        r = classify_request("explique et compare ces deux approches")
        self.assertEqual(r["type"], RequestType.REASONING)

    def test_single_reasoning_keyword_stays_text(self):
        # 1 seul mot-clé sans question longue → pas de raisonnement
        r = classify_request("explique")
        self.assertEqual(r["type"], RequestType.TEXT)

    def test_one_keyword_plus_long_question_triggers_reasoning(self):
        long_q = "pourquoi " + ("x" * 210) + " ?"
        self.assertTrue(_needs_reasoning(long_q))

    def test_humor_keyword_triggers_repartee(self):
        r = classify_request("raconte-moi une blague")
        self.assertEqual(r["type"], RequestType.REPARTEE)

    def test_expressive_punctuation_triggers_repartee(self):
        self.assertTrue(_needs_humor("quoi ?!?!?!"))
        r = classify_request("t'es sérieux !!!")
        self.assertEqual(r["type"], RequestType.REPARTEE)

    def test_image_attachment_takes_priority(self):
        att = _FakeAttachment(content_type="image/png", filename="pic.png")
        r = classify_request("explique analyse compare", attachments=[att])
        self.assertEqual(r["type"], RequestType.IMAGE)
        self.assertTrue(r["has_image"])
        self.assertIs(r["image_attachment"], att)

    def test_voice_message_detected_as_audio(self):
        att = _FakeAttachment(content_type="audio/ogg", filename="voice.ogg", is_voice_message=True)
        r = classify_request("", attachments=[att])
        self.assertEqual(r["type"], RequestType.AUDIO)
        self.assertTrue(r["has_audio"])

    def test_standard_audio_file_detected(self):
        att = _FakeAttachment(content_type="audio/mpeg", filename="song.mp3")
        r = classify_request("", attachments=[att])
        self.assertEqual(r["type"], RequestType.AUDIO)


class TestModelCascade(unittest.TestCase):
    def test_each_type_returns_nonempty_tuples(self):
        for t in (RequestType.TEXT, RequestType.REPARTEE, RequestType.IMAGE,
                  RequestType.AUDIO, RequestType.REASONING):
            cascade = get_model_cascade(t)
            self.assertGreater(len(cascade), 0, f"cascade vide pour {t}")
            for entry in cascade:
                self.assertEqual(len(entry), 2, "chaque entrée = (client_type, model)")
                self.assertTrue(all(isinstance(x, str) for x in entry))

    def test_text_default_first_is_mistral(self):
        self.assertEqual(get_model_cascade(RequestType.TEXT)[0][0], "mistral")

    def test_unknown_type_falls_back_to_text_cascade(self):
        self.assertEqual(get_model_cascade("inconnu"), get_model_cascade(RequestType.TEXT))


if __name__ == "__main__":
    unittest.main()
