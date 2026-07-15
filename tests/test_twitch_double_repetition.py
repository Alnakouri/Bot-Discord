# -*- coding: utf-8 -*-
import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_sheo_dir = os.path.join(_parent_dir, "Sheogorath")
if _sheo_dir not in sys.path:
    sys.path.insert(0, _sheo_dir)

from sheo_llm import merge_recent_responses
from tools.sonde_twitch import ends_properly, starts_with_quoted_probe, is_empty_teaser, count_sentences


def test_merge_recent_responses_none_safe():
    assert merge_recent_responses(None, None, limit=5) == []
    assert merge_recent_responses([], [], limit=5) == []


def test_merge_recent_responses_dedup_and_order():
    src1 = ["A", "B", "A"]
    src2 = ["C", "B", "D"]
    assert merge_recent_responses(src1, src2, limit=3) == ["B", "C", "D"]
    assert merge_recent_responses(src1, src2, limit=10) == ["A", "B", "C", "D"]


def test_ends_properly():
    assert ends_properly("Une réponse propre.")
    assert ends_properly("Une réponse avec emoji 🧀")
    assert ends_properly("Une réponse avec point d'exclamation !")
    assert ends_properly("Une réponse interrompue —")
    assert not ends_properly("Une réponse tronquée par le toke")
    assert not ends_properly("Mot coupé en ple")


def test_starts_with_quoted_probe():
    assert starts_with_quoted_probe('« "es-tu fou ?" » Je ne crois pas.', "@bot es-tu fou ?")
    assert starts_with_quoted_probe('"t\'es nul" Quel manque d\'élégance !', "@bot t'es nul")
    assert not starts_with_quoted_probe("Non, je ne suis pas fou.", "@bot es-tu fou ?")


def test_is_empty_teaser():
    assert is_empty_teaser("Une histoire, donc.")
    assert is_empty_teaser("Voici le conte...")
    assert is_empty_teaser("Une suite donc !")
    assert not is_empty_teaser("Je mange du fromage.")


def test_count_sentences():
    assert count_sentences("Une. Deux. Trois. Quatre. 🧀") == 4
    assert count_sentences("Une... Deux. Trois...") == 2
    assert count_sentences("") == 0


def test_extra_recent_provider_integration():
    # pytest-asyncio n'est pas installé → on pilote la coroutine avec asyncio.run.
    import asyncio
    from shared.twitch.llm import LlmMixin
    
    class DummyBot(LlmMixin):
        def __init__(self):
            self.bot_id = "test_bot"
            self.personality_prompt = "Personality"
            self.system_prompt_provider = None
            self.recent_self_responses = {"general": ["twitch_1", "twitch_2"]}
            self.logger = MagicMock()
            self.enable_viewer_memory = False
            self.key_manager = MagicMock()
            self.mistral_client = MagicMock()
            self.groq_client = MagicMock()
            self.openrouter_client = MagicMock()
            self.bot_label = "test"
            self.histories = {}
            self.channel_recent = {}
            
        def _sanitize_input(self, msg):
            return msg, False

    bot = DummyBot()
    bot.extra_recent_provider = lambda: ["discord_1", "discord_2"]

    # Mock classify_request and generate_response to prevent real network calls
    with patch("shared.smart_router.classify_request") as mock_classify, \
         patch("shared.llm_cascade.generate_response", new_callable=AsyncMock) as mock_gen:
        
        mock_classify.return_value = MagicMock()
        mock_gen.return_value = "Réponse mockée."

        asyncio.run(bot._generate_response("general", "author", "message"))

        # Verify that the generated system prompt contains elements from both twitch and discord
        called_args = mock_gen.call_args[1]
        system_prompt = called_args["system_prompt"]
        
        # Should include both Twitch ("twitch_2") and Discord ("discord_2") responses in anti-repetition block
        assert "twitch_2" in system_prompt
        assert "discord_2" in system_prompt
