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
    _needs_reasoning, _needs_humor, resolve_media_attachments,
)


class _FakeAttachment:
    """Imite discord.Attachment pour les besoins de classify_request.

    IMPORTANT : `is_voice_message` est une **methode** dans discord.py 2.x, pas un
    attribut. Le mock doit donc l'exposer comme une methode, sinon il ne teste pas
    la vraie API (c'est ce qui a laisse passer le bug ou toute piece jointe etait
    classee "vocal").
    """
    def __init__(self, content_type=None, filename="", is_voice_message=False, size=1024, url="http://x"):
        self.content_type = content_type
        self.filename = filename
        self._is_voice_message = bool(is_voice_message)
        self.size = size
        self.url = url

    def is_voice_message(self):
        return self._is_voice_message


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


class TestAddressedBanter(unittest.TestCase):
    """Phase 1 répartie : banter ADRESSÉ → classé REPARTEE (le garde `addressed` évite
    de classer en répartie une vraie question posée au bot)."""

    def test_addressed_banter_triggers_repartee(self):
        # Vanne courte sans mot-clé humour explicite : seulement si le bot est adressé.
        r = classify_request("t'es lourd aujourd'hui", addressed=True)
        self.assertEqual(r["type"], RequestType.REPARTEE)

    def test_same_banter_not_addressed_stays_text(self):
        # Rétro-compat : défaut addressed=False → comportement d'origine (TEXT).
        r = classify_request("t'es lourd aujourd'hui")
        self.assertEqual(r["type"], RequestType.TEXT)
        r2 = classify_request("t'es lourd aujourd'hui", addressed=False)
        self.assertEqual(r2["type"], RequestType.TEXT)

    def test_empty_ping_addressed_is_repartee(self):
        # Ping nu (le mortel fixe le bot) = interaction persona pure → répartie.
        self.assertEqual(classify_request("", addressed=True)["type"], RequestType.REPARTEE)

    def test_addressed_real_question_stays_serious(self):
        # Une vraie question adressée NE doit PAS être classée en répartie.
        for q in ("comment fonctionne un moteur ?", "comment tu fais ça ?",
                  "c'est quoi le roquefort ?", "explique-moi la folie",
                  "pourquoi t'es là ?"):
            r = classify_request(q, addressed=True)
            self.assertNotEqual(r["type"], RequestType.REPARTEE, f"{q!r} ne doit pas être REPARTEE")

    def test_addressed_long_message_stays_text(self):
        # Message long adressé = probablement une vraie requête, pas une vanne.
        r = classify_request("blabla " * 40, addressed=True)
        self.assertEqual(r["type"], RequestType.TEXT)


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


class TestResolveMediaAttachments(unittest.IsolatedAsyncioTestCase):
    async def test_message_with_attachments(self):
        class FakeMessage:
            attachments = ["att1"]
            reference = None
        
        msg = FakeMessage()
        res = await resolve_media_attachments(msg)
        self.assertEqual(res, ["att1"])

    async def test_message_without_attachments_but_resolved_ref_has_attachments(self):
        class FakeRef:
            message_id = 123
            class FakeResolved:
                attachments = ["att2"]
            resolved = FakeResolved()
        
        class FakeMessage:
            attachments = []
            reference = FakeRef()
            
        msg = FakeMessage()
        res = await resolve_media_attachments(msg)
        self.assertEqual(res, ["att2"])

    async def test_message_ref_fetch_success(self):
        class FakeRef:
            message_id = 123
            resolved = None

        class FakeFetchedMessage:
            attachments = ["att3"]

        class FakeChannel:
            async def fetch_message(self, message_id):
                if message_id == 123:
                    return FakeFetchedMessage()
                return None

        class FakeMessage:
            attachments = []
            reference = FakeRef()
            channel = FakeChannel()

        msg = FakeMessage()
        res = await resolve_media_attachments(msg)
        self.assertEqual(res, ["att3"])

    async def test_message_ref_fetch_failure(self):
        class FakeRef:
            message_id = 123
            resolved = None

        class FakeChannel:
            async def fetch_message(self, message_id):
                raise RuntimeError("fetch failed")

        class FakeMessage:
            attachments = ["att_fallback"]
            reference = FakeRef()
            channel = FakeChannel()

        msg = FakeMessage()
        res = await resolve_media_attachments(msg)
        self.assertEqual(res, ["att_fallback"])

    async def test_resolved_ref_without_attachments_skips_fetch(self):
        # Ref déjà résolue (cache gateway) sans pièce jointe : ses attachments
        # font foi → aucun fetch HTTP (cas courant : reply au bot lui-même).
        class FakeRef:
            message_id = 123
            class FakeResolved:
                attachments = []
            resolved = FakeResolved()

        class FakeChannel:
            async def fetch_message(self, message_id):
                raise AssertionError("fetch_message ne doit pas être appelé")

        class FakeMessage:
            attachments = []
            reference = FakeRef()
            channel = FakeChannel()

        msg = FakeMessage()
        res = await resolve_media_attachments(msg)
        self.assertEqual(res, [])


class TestVoiceMessageDetection(unittest.TestCase):
    """Anti-retour : discord.Attachment.is_voice_message est une METHODE.

    Un `getattr(att, "is_voice_message", False)` nu renvoie la methode liee, donc
    une valeur toujours vraie : toutes les images partaient en cascade AUDIO.
    """

    def test_image_is_not_a_voice_message(self):
        att = _FakeAttachment(content_type="image/webp", filename="photo.webp")
        r = classify_request("", [att])
        self.assertEqual(r["type"], RequestType.IMAGE)
        self.assertTrue(r["has_image"])
        self.assertFalse(r["has_audio"])

    def test_real_voice_message_still_detected(self):
        att = _FakeAttachment(content_type="audio/ogg", filename="voice-message.ogg",
                              is_voice_message=True)
        r = classify_request("", [att])
        self.assertEqual(r["type"], RequestType.AUDIO)
        self.assertTrue(r["has_audio"])
        self.assertFalse(r["has_image"])

    def test_method_style_flag_is_called_not_truthy_tested(self):
        from shared.smart_router import _is_voice_message

        class _MethodStyle:
            def is_voice_message(self):
                return False

        class _AttributeStyle:
            is_voice_message = False

        self.assertFalse(_is_voice_message(_MethodStyle()))
        self.assertFalse(_is_voice_message(_AttributeStyle()))
        self.assertFalse(_is_voice_message(object()))


if __name__ == "__main__":
    unittest.main()
