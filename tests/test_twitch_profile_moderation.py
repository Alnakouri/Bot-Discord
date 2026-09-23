# -*- coding: utf-8 -*-
"""Vérifie que update_profile signale un refus de bio par la modération Twitch.

Sur 400 'failed moderation', update_profile doit rendre 'bio_refusee' (utilisé par
daily_profile pour basculer sur la bio fixe).
Sur toute autre erreur ou sur 200, il doit rendre None.
"""
import asyncio
import logging
import os
import sys
from unittest.mock import AsyncMock

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.twitch import profile
from shared.twitch.profile import TwitchProfile


def _make_session_cls(status: int, text_content: str):
    class _FakeResponse:
        def __init__(self):
            self.status = status

        async def text(self):
            return text_content

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        def put(self, *args, **kwargs):
            return _FakeResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    return _FakeSession


def test_bio_refusee_par_moderation(monkeypatch):
    """Twitch 400 moderation -> 'bio_refusee'."""
    monkeypatch.setattr(
        profile.aiohttp,
        "ClientSession",
        _make_session_cls(400, '{"status":400,"message":"Description failed moderation."}'),
    )
    logger = logging.getLogger("test_twitch_profile")
    auth = AsyncMock()
    auth.get_valid_token = AsyncMock(return_value="tok")
    tp = TwitchProfile("johnny", logger, "cid", auth)

    res = asyncio.run(tp.update_profile(bio="x"))
    assert res == "bio_refusee"


def test_bio_autre_erreur_400(monkeypatch):
    """Twitch 400 autre que modération -> None."""
    monkeypatch.setattr(
        profile.aiohttp,
        "ClientSession",
        _make_session_cls(400, '{"status":400,"message":"Invalid parameter"}'),
    )
    logger = logging.getLogger("test_twitch_profile")
    auth = AsyncMock()
    auth.get_valid_token = AsyncMock(return_value="tok")
    tp = TwitchProfile("johnny", logger, "cid", auth)

    res = asyncio.run(tp.update_profile(bio="x"))
    assert res is None


def test_bio_succes_200(monkeypatch):
    """Twitch 200 -> None."""
    monkeypatch.setattr(
        profile.aiohttp,
        "ClientSession",
        _make_session_cls(200, ""),
    )
    logger = logging.getLogger("test_twitch_profile")
    auth = AsyncMock()
    auth.get_valid_token = AsyncMock(return_value="tok")
    tp = TwitchProfile("johnny", logger, "cid", auth)

    res = asyncio.run(tp.update_profile(bio="x"))
    assert res is None
