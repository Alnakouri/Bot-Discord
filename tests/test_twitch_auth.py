# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from shared.twitch.auth import TwitchAuth


class _AsyncContextManager:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def _creer_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    logger = MagicMock()
    auth = TwitchAuth(
        bot_id="sugar",
        logger=logger,
        client_id="cid",
        client_secret="csec",
        default_token="mock_token",
        default_refresh="mock_refresh",
    )
    return auth, logger


@pytest.mark.asyncio
async def test_401_aucun_warning_emis(tmp_path, monkeypatch):
    """Un token validé avec 401 n'émet aucun WARNING (cas nominal au redémarrage)."""
    auth, logger = _creer_auth(tmp_path, monkeypatch)

    mock_resp = MagicMock()
    mock_resp.status = 401

    mock_session = MagicMock()
    mock_session.get.return_value = _AsyncContextManager(mock_resp)

    with patch("aiohttp.ClientSession", return_value=_AsyncContextManager(mock_session)):
        valide = await auth.validate_token()

    assert valide is False
    logger.warning.assert_not_called()
    logger.info.assert_any_call("🔄 [TWITCH_CHAT:sugar] Jeton expiré (401), rafraîchissement…")


@pytest.mark.asyncio
async def test_500_emet_warning(tmp_path, monkeypatch):
    """Un code autre que 401 (ex: 500) émet un WARNING."""
    auth, logger = _creer_auth(tmp_path, monkeypatch)

    mock_resp = MagicMock()
    mock_resp.status = 500

    mock_session = MagicMock()
    mock_session.get.return_value = _AsyncContextManager(mock_resp)

    with patch("aiohttp.ClientSession", return_value=_AsyncContextManager(mock_session)):
        valide = await auth.validate_token()

    assert valide is False
    logger.warning.assert_called_once_with("⚠️ [TWITCH_CHAT:sugar] Token invalide (code 500)")


@pytest.mark.asyncio
async def test_refresh_echec_emet_error(tmp_path, monkeypatch):
    """Un refresh en échec émet un ERROR."""
    auth, logger = _creer_auth(tmp_path, monkeypatch)

    mock_resp = MagicMock()
    mock_resp.status = 400
    mock_resp.text = AsyncMock(return_value="Invalid refresh token")

    mock_session = MagicMock()
    mock_session.post.return_value = _AsyncContextManager(mock_resp)

    with patch("aiohttp.ClientSession", return_value=_AsyncContextManager(mock_session)):
        reussi = await auth.refresh()

    assert reussi is False
    logger.error.assert_called_once_with(
        "❌ [TWITCH_CHAT:sugar] Échec du refresh token (400): Invalid refresh token"
    )
