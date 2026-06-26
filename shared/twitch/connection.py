# -*- coding: utf-8 -*-
import os
import time
import json
import asyncio
from datetime import datetime
import aiohttp
from pathlib import Path

DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent.parent.parent / "data"))

class ConnectionMixin:
    async def run(self):
        self._stopped = False
        backoff = 1
        
        # Démarre la boucle de refresh proactif
        refresh_task = asyncio.create_task(self._token_refresh_loop())

        eventsub_task = None
        voice_task = None

        try:
            while not self._stopped:
                try:
                    token = await self.auth.get_valid_token()
                    if not token:
                        self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Impossible de récupérer un token. Réessai dans {backoff}s...")
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 60)
                        continue

                    # Application du profil Twitch autonome quotidien en arrière-plan
                    today = datetime.now().strftime("%Y-%m-%d")
                    if self._profile_day != today:
                        asyncio.create_task(self._ensure_daily_profile())

                    # Démarrage de Twitch EventSub
                    if self.enable_eventsub and not self.eventsub_active:
                        eventsub_task = asyncio.create_task(self._start_eventsub())

                    # Démarrage du client d'écoute voix (STT)
                    if self.enable_voice_listen and voice_task is None:
                        voice_task = asyncio.create_task(self._start_voice_listen())

                    # On tente de se connecter et de boucler sur les messages
                    await self._connect_and_loop(token)

                    if self._stopped:
                        break

                    # Reconnexion en cas de déconnexion imprévue
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur boucle de vie: {e}", exc_info=True)
                    if self._stopped:
                        break
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
        finally:
            refresh_task.cancel()
            if eventsub_task:
                eventsub_task.cancel()
            if voice_task:
                voice_task.cancel()
            # Sauvegarde finale des viewers
            path = os.path.join(DATA_DIR, f"twitch_viewers_{self.bot_id}.json")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.viewers_state, f, indent=2)
            except Exception:
                pass
            self.logger.info(f"👋 [TWITCH_CHAT:{self.bot_id}] Arrêt de la boucle Twitch Chat.")

    async def _token_refresh_loop(self):
        while not self._stopped:
            try:
                await asyncio.sleep(60)
                now = time.time()
                if self.auth.expires_at and (self.auth.expires_at - now < 1800):
                    self.logger.info(f"🔄 [TWITCH_CHAT:{self.bot_id}] Token proche de l'expiration. Refresh proactif...")
                    await self.auth.refresh()

                # Contrôle léger pour la bascule de minuit
                today = datetime.now().strftime("%Y-%m-%d")
                if self._profile_day != today:
                    self.logger.info(f"🕛 [TWITCH_CHAT:{self.bot_id}] Passage à un nouveau jour ({today}). Mise à jour du profil...")
                    asyncio.create_task(self._ensure_daily_profile())
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur loop refresh proactif: {e}")

    async def _connect_and_loop(self, token: str):
        timeout = aiohttp.ClientTimeout(total=None)
        url = "wss://irc-ws.chat.twitch.tv:443"
        
        pass_token = token
        if not pass_token.startswith("oauth:"):
            pass_token = "oauth:" + pass_token

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(url, heartbeat=30) as ws:
                self.ws = ws
                await ws.send_str("CAP REQ :twitch.tv/tags twitch.tv/commands")
                await ws.send_str(f"PASS {pass_token}")
                await ws.send_str(f"NICK {self.username.lower()}")
                
                for channel in self.channels:
                    await ws.send_str(f"JOIN #{channel}")
                    self.logger.info(f"🔌 [TWITCH_CHAT:{self.bot_id}] Connecté à #{channel} en tant que {self.username}")

                async for msg in ws:
                    if self._stopped:
                        break
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] WebSocket fermé : {msg.data}")
                            break
                        continue

                    for line in msg.data.split("\r\n"):
                        if not line:
                            continue

                        if line.startswith("PING"):
                            await ws.send_str("PONG :tmi.twitch.tv")
                            continue

                        self.logger.debug(f"RAW> {line}")

                        if "Login authentication failed" in line:
                            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Auth échouée. Tentative de refresh...")
                            await self.auth.refresh()
                            return

                        tags = {}
                        if line.startswith("@"):
                            tags = self._parse_tags(line)

                        # 1. Traitement de USERNOTICE (Subs, Raids, etc.)
                        if "USERNOTICE" in line:
                            un_match = self.USERNOTICE_RE.match(line)
                            if un_match:
                                chan = un_match.group("chan")
                                msg_text = un_match.group("msg") or ""
                                if self.enable_events:
                                    asyncio.create_task(self._handle_usernotice(chan, tags, msg_text, ws))
                                continue

                        m = self.PRIVMSG_RE.match(line)
                        if not m:
                            continue

                        author = m.group("user")
                        chan = m.group("chan")
                        text = m.group("msg").strip()

                        # Anti-boucle : son propre pseudo + les autres bots connus
                        # (configurés via TWITCH_PEER_BOTS). Évite que deux bots se
                        # répondent / s'accueillent mutuellement.
                        if author.lower() in self.known_bots:
                            continue

                        await self._handle_privmsg(chan, author, text, tags, ws)
