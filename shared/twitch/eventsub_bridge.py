# -*- coding: utf-8 -*-
import aiohttp
import asyncio
import time

from shared.twitch.sanitize import send_chat_safe

class EventSubMixin:
    async def get_broadcaster_id(self) -> str | None:
        # Si on a le token broadcaster, on résout SON propre user-id (helix/users sans
        # login = propriétaire du token) → garantit broadcaster_user_id == owner du token,
        # condition obligatoire pour s'abonner aux events « channel ».
        eventsub_auth = self.broadcaster_auth or self.auth
        token = await eventsub_auth.get_valid_token()
        if not token:
            return None
        if self.broadcaster_auth:
            url = "https://api.twitch.tv/helix/users"
        else:
            url = f"https://api.twitch.tv/helix/users?login={self.channels[0]}"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("data"):
                            return data["data"][0]["id"]
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT] Erreur récupération broadcaster_id: {e}")
        return None

    async def _start_eventsub(self):
        try:
            from shared.twitch_eventsub import TwitchEventSub
        except ImportError as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Module EventSub non disponible: {e}")
            return

        broadcaster_id = await self.get_broadcaster_id()
        if not broadcaster_id:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Impossible de démarrer EventSub: broadcaster_id non récupéré.")
            return

        self.logger.info(f"📡 [TWITCH_CHAT:{self.bot_id}] broadcaster_id récupéré: {broadcaster_id}")
        self.eventsub_active = True
        
        async def emit_callback(text: str) -> bool:
            if self.ws and not self.ws.closed and self.channels:
                chan = self.channels[0]
                now = time.time()
                while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
                    self.global_msg_timestamps.popleft()
                if len(self.global_msg_timestamps) >= 18:
                    self.logger.warning(f"🚨 [TWITCH_CHAT:{self.bot_id}] EventSub callback: rate limit global atteint. Message ignoré.")
                    return False
                self.global_msg_timestamps.append(now)
                await send_chat_safe(self.ws, chan, text, bot_id=self.bot_id, logger=self.logger)
                return True
            return False

        self.eventsub_client = TwitchEventSub(
            bot_id=self.bot_id,
            logger=self.logger,
            auth=self.broadcaster_auth or self.auth,
            client_id=self.client_id,
            broadcaster_id=broadcaster_id,
            emit_callback=emit_callback,
            subscriptions=self.eventsub_subscriptions,
            reward_map=self.eventsub_reward_map,
            bot_label=self.bot_label,
            personality_prompt=self.personality_prompt,
            key_manager=self.key_manager,
            mistral_client=self.mistral_client,
            groq_client=self.groq_client,
            openrouter_client=self.openrouter_client,
            commands=self.commands
        )
        try:
            await self.eventsub_client.run()
        except asyncio.CancelledError:
            self.eventsub_client.stop()
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur dans la tâche EventSub: {e}")
        finally:
            self.eventsub_active = False
