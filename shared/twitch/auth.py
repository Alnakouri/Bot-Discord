# -*- coding: utf-8 -*-
import os
import json
import time
import aiohttp
from pathlib import Path

DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent.parent.parent / "data"))

class TwitchAuth:
    """
    Gère le stockage, la validation et le rafraîchissement des tokens Twitch User.
    """
    def __init__(self, bot_id: str, logger, client_id: str, client_secret: str, default_token: str | None = None, default_refresh: str | None = None):
        self.bot_id = bot_id
        self.logger = logger
        self.client_id = client_id
        self.client_secret = client_secret
        self.file_path = os.path.join(DATA_DIR, f"twitch_chat_auth_{bot_id}.json")
        self.access_token = None
        self.refresh_token = None
        self.expires_at = 0
        self._load(default_token, default_refresh)

    def _load(self, default_token: str | None, default_refresh: str | None):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token")
                    self.refresh_token = data.get("refresh_token")
                    self.expires_at = data.get("expires_at", 0)
                    self.logger.info(f"🔑 [TWITCH_CHAT:{self.bot_id}] Chargement des tokens depuis {self.file_path}")
                    return
            except Exception as e:
                self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur lecture auth JSON: {e}")

        # Amorçage avec les valeurs par défaut
        if default_token:
            token = default_token
            if token.startswith("oauth:"):
                token = token[6:]
            self.access_token = token
        if default_refresh:
            self.refresh_token = default_refresh
        self.expires_at = 0

    def _save(self):
        data = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at
        }
        tmp_path = self.file_path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self.file_path)
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Échec de la sauvegarde auth JSON: {e}")

    async def get_valid_token(self) -> str | None:
        now = time.time()
        if self.access_token and now + 300 < self.expires_at:
            return self.access_token

        if self.access_token:
            valid = await self.validate_token()
            if valid and time.time() + 300 < self.expires_at:
                return self.access_token

        if self.refresh_token:
            success = await self.refresh()
            if success:
                return self.access_token

        return self.access_token

    async def validate_token(self) -> bool:
        if not self.access_token:
            return False
        url = "https://id.twitch.tv/oauth2/validate"
        headers = {"Authorization": f"OAuth {self.access_token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        expires_in = data.get("expires_in", 0)
                        self.expires_at = time.time() + expires_in
                        self._save()
                        self.logger.info(f"✅ [TWITCH_CHAT:{self.bot_id}] Token validé (expire dans {expires_in}s)")
                        return True
                    elif resp.status == 401:
                        self.logger.info(f"🔄 [TWITCH_CHAT:{self.bot_id}] Jeton expiré (401), rafraîchissement…")
                        return False
                    else:
                        self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] Token invalide (code {resp.status})")
                        return False
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur validation du token: {e}")
            return False

    async def refresh(self) -> bool:
        if not self.refresh_token:
            self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] Pas de refresh token disponible.")
            return False

        url = "https://id.twitch.tv/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, timeout=10) as resp:
                    if resp.status == 200:
                        resp_data = await resp.json()
                        self.access_token = resp_data["access_token"]
                        if "refresh_token" in resp_data:
                            self.refresh_token = resp_data["refresh_token"]
                        expires_in = resp_data.get("expires_in", 3600)
                        self.expires_at = time.time() + expires_in
                        self._save()
                        self.logger.info(f"🔄 [TWITCH_CHAT:{self.bot_id}] Token rafraîchi avec succès. Expire dans {expires_in}s")
                        return True
                    else:
                        err_text = await resp.text()
                        self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Échec du refresh token ({resp.status}): {err_text}")
                        return False
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur lors du refresh: {e}")
            return False
