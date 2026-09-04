import os
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.smart_router import classify_request, RequestType

class FakeAttachment:
    def __init__(self, content_type=None, filename="", is_voice_message=False, size=1024, url="http://x"):
        self.content_type = content_type
        self.filename = filename
        self._is_voice_message = bool(is_voice_message)
        self.size = size
        self.url = url

    def is_voice_message(self):
        return self._is_voice_message

class TestSheoImages(unittest.IsolatedAsyncioTestCase):
    def test_smart_router_image_fallback_to_extension(self):
        """Vérifie que les 7 copies du routeur acceptent une image par son extension si content_type manque."""
        # Test avec le routeur de shared
        att = FakeAttachment(content_type=None, filename="photo.jpeg")
        res = classify_request("Regarde", [att])
        self.assertTrue(res["has_image"])
        
        att2 = FakeAttachment(content_type="image/heic", filename="photo.heic")
        res2 = classify_request("Regarde", [att2])
        self.assertTrue(res2["has_image"])
        
        # Vérification des 7 copies
        router_paths = [
            "shared/smart_router.py",
            "Sheogorath/core/smart_router.py",
            "MalenaBot/core/smart_router.py",
            "MaiqBot/core/smart_router.py",
            "JohnnyBot/core/smart_router.py",
            "SugarBot/core/smart_router.py",
            "Alfred/core/smart_router.py"
        ]
        
        count = 0
        for path in router_paths:
            full_path = os.path.join(_parent_dir, path)
            if os.path.exists(full_path):
                count += 1
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    self.assertTrue('filename.endswith(IMAGE_EXTENSIONS)' in content or 'ct.startswith("image/")' in content)
                    
        self.assertEqual(count, 7, f"Toutes les copies de smart_router.py n'ont pas été trouvées. Trouvé: {count}/7")

    async def test_sheo_prompt_montage_does_not_assert_image_without_verification(self):
        """
        Si has_image local est vrai mais que le téléchargement échoue (media_data None), 
        le prompt ne doit pas exiger une preuve d'image.
        """
        import sys
        sheo_dir = os.path.join(_parent_dir, 'Sheogorath')
        if sheo_dir not in sys.path:
            sys.path.insert(0, sheo_dir)
        import bot_sheogorath as sheo
        
        mock_message = MagicMock()
        mock_message.author.bot = False
        mock_message.author.id = 123
        mock_message.author.name = "TestUser"
        mock_message.content = "Regarde"
        mock_message.channel = AsyncMock()
        mock_message.channel.send = AsyncMock()
        mock_message.channel.id = 456
        
        class AsyncIter:
            def __init__(self, items): self.items = items
            async def __aiter__(self):
                for item in self.items: yield item
        
        mock_message.channel.history = MagicMock(return_value=AsyncIter([]))
        
        att = FakeAttachment(content_type="image/jpeg", filename="test.jpg")
        mock_message.attachments = [att]
        
        # On simule un échec de téléchargement
        with patch("bot_sheogorath.download_media", new_callable=AsyncMock) as mock_dl:
            mock_dl.return_value = (None, "image/jpeg")  # Échec du téléchargement
    
            # On mocke l'appel LLM pour capturer le prompt généré
            with patch("bot_sheogorath.get_model_cascade") as mock_cascade:
                mock_cascade.return_value = [("gemini", "test-model")]
    
                # ⚠️ Sans clé, la branche Gemini fait `continue` : le test passait en
                # local (clés présentes) et tombait en CI (aucune clé).
                with (
                    patch("bot_sheogorath.key_manager.get_key", return_value="FAKE_KEY"),
                    patch("bot_sheogorath.get_safe_genai_client") as mock_get_client,
                ):
                    mock_client = MagicMock()
                    mock_resp = MagicMock()
                    mock_resp.text = "Mock response"
                    mock_client.models.generate_content.return_value = mock_resp
                    mock_get_client.return_value = mock_client
    
                    # Mock des dépendances pour éviter qu'il s'arrête prématurément
                    with patch("bot_sheogorath._check_global_rate_limit", return_value=False, create=True):
                        with patch("bot_sheogorath.fact_brain.get_facts", return_value=[]):
                            with patch("bot_sheogorath.faveur_system.get_rank_context", return_value=""):
                                with patch("discord.Client.user", new_callable=unittest.mock.PropertyMock) as mock_user:
                                    mock_user.return_value = MagicMock(id=999)
                                    await sheo.on_message(mock_message)
    
                                # Vérifier le prompt généré
                                call_args = mock_client.models.generate_content.call_args
                                self.assertIsNotNone(
                                    call_args,
                                    "La branche Gemini n'a jamais été atteinte : le prompt "
                                    "n'a pas pu être inspecté, ce test ne prouve rien tant "
                                    "qu'il ne passe pas par là.",
                                )
                                
                                contents = call_args.kwargs.get('contents') or call_args.args[1]
                                # Parcourir les parts
                                prompt_text = str(contents)
                                
                                self.assertNotIn("a envoyé une IMAGE", prompt_text)
                                self.assertNotIn("prouve que tu as vu l'image", prompt_text)

    async def test_sheo_gemini_multimodal_branch_is_active(self):
        """
        Vérifie que la branche qui SERT les images génère bien un payload multimodal
        quand il y a media_data.

        ⚠️ Ce test portait sur la branche OpenRouter jusqu'au 2026-09-05. OpenRouter a
        été retiré (cf. `test_openrouter_est_retire.py`) et, de toute façon, la cascade
        IMAGE ne rendait que `gemini` : la branche testée n'était jamais atteinte. La
        couverture est déplacée là où le média passe réellement.
        """
        import sys
        sheo_dir = os.path.join(_parent_dir, 'Sheogorath')
        if sheo_dir not in sys.path:
            sys.path.insert(0, sheo_dir)
        import bot_sheogorath as sheo
    
        mock_message = MagicMock()
        mock_message.author.bot = False
        mock_message.author.id = 123
        mock_message.author.name = "TestUser"
        mock_message.content = "Regarde"
        mock_message.channel = AsyncMock()
        mock_message.channel.send = AsyncMock()
        mock_message.channel.id = 456
        
        class AsyncIter:
            def __init__(self, items): self.items = items
            async def __aiter__(self):
                for item in self.items: yield item
        
        mock_message.channel.history = MagicMock(return_value=AsyncIter([]))
        
        att = FakeAttachment(content_type="image/jpeg", filename="test.jpg")
        mock_message.attachments = [att]
        
        with patch("bot_sheogorath.download_media", new_callable=AsyncMock) as mock_dl:
            mock_dl.return_value = (b"fake_image_data", "image/jpeg")
            
            with patch("bot_sheogorath.get_model_cascade") as mock_cascade:
                mock_cascade.return_value = [("gemini", "test-model")]

                # ⚠️ Sans clé, la branche Gemini fait `continue` : le test passerait en
                # local (clés présentes) et tomberait en CI (aucune clé).
                with (
                    patch("bot_sheogorath.key_manager.get_key", return_value="FAKE_KEY"),
                    patch("bot_sheogorath.get_safe_genai_client") as mock_get_client,
                ):
                    # MagicMock, PAS AsyncMock : le code appelle `generate_content` via
                    # `asyncio.to_thread`, donc de façon SYNCHRONE. Un AsyncMock rendrait
                    # une coroutine jamais attendue, l'exception serait avalée par la
                    # cascade et la branche ne serait pas parcourue jusqu'au bout.
                    mock_client = MagicMock()
                    mock_resp = MagicMock()
                    mock_resp.text = "Gemini response"
                    mock_resp.candidates[0].content.parts[0].function_call = None
                    mock_client.models.generate_content.return_value = mock_resp
                    mock_get_client.return_value = mock_client

                    with patch("bot_sheogorath._check_global_rate_limit", return_value=False, create=True):
                        with patch("bot_sheogorath.fact_brain.get_facts", return_value=[]):
                            with patch("bot_sheogorath.faveur_system.get_rank_context", return_value=""):
                                with patch("discord.Client.user", new_callable=unittest.mock.PropertyMock) as mock_user:
                                    mock_user.return_value = MagicMock(id=999)
                                    await sheo.on_message(mock_message)

                                call_args = mock_client.models.generate_content.call_args
                                self.assertIsNotNone(
                                    call_args,
                                    "La branche Gemini n'a jamais été atteinte : ce test "
                                    "ne prouve rien tant qu'il ne passe pas par là.",
                                )

                                contents = call_args.kwargs.get("contents") or call_args.args[1]
                                # Le dernier tour porte le texte ET l'image en inline_data.
                                parts = contents[-1].parts
                                octets = [
                                    p.inline_data.data for p in parts
                                    if getattr(p, "inline_data", None) is not None
                                ]
                                self.assertEqual(
                                    octets, [b"fake_image_data"],
                                    "l'image n'est pas arrivée jusqu'au modèle",
                                )

if __name__ == "__main__":
    unittest.main()
