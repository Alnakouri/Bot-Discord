import os
import json
import logging
import asyncio
import aiohttp
import time
from datetime import datetime

logger = logging.getLogger("twitch_eventsub")

class TwitchEventSub:
    def __init__(self, bot_id: str, logger, auth, client_id: str,
                 broadcaster_id: str, emit_callback, subscriptions: list[str],
                 reward_map: dict | None = None, bot_label: str = None,
                 personality_prompt: str = None, key_manager = None,
                 mistral_client = None, groq_client = None, openrouter_client = None,
                 commands: dict = None):
        self.bot_id = bot_id
        self.logger = logger
        self.auth = auth
        self.client_id = client_id
        self.broadcaster_id = broadcaster_id
        self.emit_callback = emit_callback
        self.subscriptions = subscriptions
        self.reward_map = reward_map or {}
        self.bot_label = bot_label or bot_id
        self.personality_prompt = personality_prompt or ""
        self.key_manager = key_manager
        self.mistral_client = mistral_client
        self.groq_client = groq_client
        self.openrouter_client = openrouter_client
        self.commands = commands or {}

        self.ws_url = "wss://eventsub.wss.twitch.tv/ws"
        self._stopped = False
        self.active_subs = []
        self.cooldowns = {} # key -> timestamp

    async def run(self):
        self.logger.info(f"📡 [TWITCH_EVENTSUB:{self.bot_id}] Démarrage du client EventSub...")
        backoff = 1
        while not self._stopped:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(self.ws_url, heartbeat=15.0) as ws:
                        self.logger.info(f"🔌 [TWITCH_EVENTSUB:{self.bot_id}] Connecté au WebSocket Twitch EventSub.")
                        backoff = 1
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                await self._handle_message(data, ws)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except Exception as e:
                self.logger.error(f"❌ [TWITCH_EVENTSUB:{self.bot_id}] Erreur WebSocket: {e}")
            
            if self._stopped:
                break
            
            self.logger.info(f"⏳ [TWITCH_EVENTSUB:{self.bot_id}] Reconnexion dans {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    def stop(self):
        self._stopped = True

    async def _handle_message(self, data: dict, ws):
        metadata = data.get("metadata", {})
        msg_type = metadata.get("message_type")
        payload = data.get("payload", {})

        if msg_type == "session_welcome":
            session_id = payload.get("session", {}).get("id")
            self.logger.info(f"🔑 [TWITCH_EVENTSUB:{self.bot_id}] Session bienvenue reçue. ID: {session_id}")
            # Enregistrer les abonnements
            await self._subscribe_all(session_id)

        elif msg_type == "session_keepalive":
            pass

        elif msg_type == "session_reconnect":
            reconnect_url = payload.get("session", {}).get("reconnect_url")
            if reconnect_url:
                self.logger.info(f"🔄 [TWITCH_EVENTSUB:{self.bot_id}] Reconnexion requise vers: {reconnect_url}")
                self.ws_url = reconnect_url

        elif msg_type == "notification":
            sub_type = payload.get("subscription", {}).get("type")
            event = payload.get("event", {})
            self.logger.info(f"🔔 [TWITCH_EVENTSUB:{self.bot_id}] Événement reçu: {sub_type}")
            await self._process_event(sub_type, event)

    async def _subscribe_all(self, session_id: str):
        token = await self.auth.get_valid_token()
        if not token:
            self.logger.error(f"❌ [TWITCH_EVENTSUB:{self.bot_id}] Impossible de s'abonner : pas de token valide.")
            return

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        subs_config = {
            "channel.channel_points_custom_reward_redemption.add": {
                "version": "1",
                "condition": {"broadcaster_user_id": self.broadcaster_id}
            },
            "channel.follow": {
                "version": "2",
                "condition": {"broadcaster_user_id": self.broadcaster_id, "moderator_user_id": self.broadcaster_id}
            },
            "channel.raid": {
                "version": "1",
                "condition": {"to_broadcaster_user_id": self.broadcaster_id}
            },
            "channel.hype_train.begin": {
                "version": "2",
                "condition": {"broadcaster_user_id": self.broadcaster_id}
            },
            "channel.hype_train.end": {
                "version": "2",
                "condition": {"broadcaster_user_id": self.broadcaster_id}
            },
            "channel.poll.begin": {
                "version": "1",
                "condition": {"broadcaster_user_id": self.broadcaster_id}
            },
            "channel.poll.end": {
                "version": "1",
                "condition": {"broadcaster_user_id": self.broadcaster_id}
            }
        }

        self.active_subs = []
        async with aiohttp.ClientSession() as session:
            for sub_type in self.subscriptions:
                cfg = subs_config.get(sub_type)
                if not cfg:
                    continue
                body = {
                    "type": sub_type,
                    "version": cfg["version"],
                    "condition": cfg["condition"],
                    "transport": {
                        "method": "websocket",
                        "session_id": session_id
                    }
                }
                url = "https://api.twitch.tv/helix/eventsub/subscriptions"
                try:
                    async with session.post(url, headers=headers, json=body) as resp:
                        if resp.status in (200, 202):
                            self.logger.info(f"✅ [TWITCH_EVENTSUB:{self.bot_id}] Abonné à {sub_type}")
                            self.active_subs.append(sub_type)
                        else:
                            err = await resp.text()
                            self.logger.warning(f"⚠️ [TWITCH_EVENTSUB:{self.bot_id}] Échec abonnement {sub_type} (code {resp.status}): {err}")
                except Exception as e:
                    self.logger.error(f"❌ [TWITCH_EVENTSUB:{self.bot_id}] Erreur POST subscribe {sub_type}: {e}")

    async def _process_event(self, sub_type: str, event: dict):
        # Cooldown par type d'événement pour éviter le spam (cooldown de 5s par type)
        now = time.time()
        last_time = self.cooldowns.get(sub_type, 0)
        if now - last_time < 5.0:
            self.logger.info(f"⏳ [TWITCH_EVENTSUB:{self.bot_id}] Événement {sub_type} ignoré (cooldown)")
            return
        self.cooldowns[sub_type] = now

        user_name = event.get("user_name", "Un spectateur")
        user_input = event.get("user_input", "")

        if sub_type == "channel.channel_points_custom_reward_redemption.add":
            reward = event.get("reward", {})
            title = reward.get("title", "")
            self.logger.info(f"🎁 [TWITCH_EVENTSUB:{self.bot_id}] Custom reward redeemed: {title} par {user_name}")

            # Check mapping
            action = self.reward_map.get(title)
            if action:
                # Si c'est mappé sur une commande
                cmd_func = self.commands.get(action)
                if cmd_func:
                    try:
                        if asyncio.iscoroutinefunction(cmd_func):
                            res = await cmd_func(user_name, user_input)
                        else:
                            res = cmd_func(user_name, user_input)
                        if res:
                            await self.emit_callback(res)
                    except Exception as e:
                        self.logger.error(f"Erreur callback commande EventSub: {e}")
                    return
            
            # Sinon réaction LLM courte
            prompt = f"Le spectateur @{user_name} a activé la récompense de chaîne '{title}' ! Réagis courtement avec ton franc-parler de personnage."
            if user_input:
                prompt += f" Message de l'utilisateur : {user_input}"
            await self._generate_and_emit(prompt)

        elif sub_type == "channel.follow":
            prompt = f"Le spectateur @{user_name} vient de follow la chaîne ! Remercie-le ou taquine-le courtement dans ton personnage."
            await self._generate_and_emit(prompt)

        elif sub_type == "channel.raid":
            raider = event.get("from_broadcaster_user_name", "Un streamer")
            viewers = event.get("viewers", 0)
            prompt = f"Le streamer @{raider} lance un raid avec {viewers} spectateurs ! Accueille-les courtement avec ta personnalité."
            await self._generate_and_emit(prompt)

        elif sub_type == "channel.hype_train.begin":
            prompt = "Un train de la Hype commence ! Encourage tout le monde à participer de manière excitée ou cynique selon ton personnage."
            await self._generate_and_emit(prompt)

        elif sub_type == "channel.hype_train.end":
            level = event.get("level", 1)
            prompt = f"Le train de la Hype est terminé au niveau {level} ! Félicite ou raille les spectateurs selon ta personnalité."
            await self._generate_and_emit(prompt)

        elif sub_type == "channel.poll.begin":
            title = event.get("title", "")
            prompt = f"Un sondage vient de commencer : '{title}'. Invite les gens à voter de façon amusante."
            await self._generate_and_emit(prompt)

        elif sub_type == "channel.poll.end":
            title = event.get("title", "")
            prompt = f"Le sondage '{title}' est terminé. Fais un commentaire amusant ou cynique là-dessus."
            await self._generate_and_emit(prompt)

    async def _generate_and_emit(self, prompt: str):
        if not self.key_manager:
            return
        
        from shared.llm_cascade import generate_response
        from shared.smart_router import RequestType
        
        try:
            text = await generate_response(
                routing={"type": RequestType.TEXT, "reason": "twitch_eventsub_reaction"},
                system_prompt=self.personality_prompt,
                transcript="",
                user_message=prompt,
                conversation_history=[],
                media_data=None,
                mime_type="",
                key_manager=self.key_manager,
                mistral_client=self.mistral_client,
                groq_client=self.groq_client,
                openrouter_client=self.openrouter_client,
                bot_label=self.bot_label,
                temperature=0.9,
                max_tokens=60
            )
            if text:
                text = " ".join(text.split()).strip()
                from shared.twitch_chat import TwitchChatBot
                text = TwitchChatBot._strip_stage_directions(text)
                text = text.strip('"\'')
                await self.emit_callback(text)
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_EVENTSUB:{self.bot_id}] Erreur génération de réaction EventSub: {e}")
