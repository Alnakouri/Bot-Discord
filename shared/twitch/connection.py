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
        # Superviseur d'écoute micro : applique en continu le toggle du dashboard
        # (activable/désactivable À CHAUD, sans redémarrer le bot).
        voice_task = asyncio.create_task(self._voice_supervisor())

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
            except Exception as e:
                self.logger.debug(f"[TWITCH] sauvegarde finale des viewers impossible : {e}")
            self.logger.info(f"👋 [TWITCH_CHAT:{self.bot_id}] Arrêt de la boucle Twitch Chat.")

    def _desired_voice_listen(self) -> bool:
        """État SOUHAITÉ de l'écoute micro. Le dashboard (data/twitch_config.json →
        listen.enabled) prime, relu à chaque tick pour un toggle à chaud ; à défaut on
        retombe sur la valeur d'initialisation. Toute erreur de lecture = état courant."""
        path = os.path.join(DATA_DIR, "twitch_config.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            listen = ((data.get(self.bot_id) or {}).get("listen") or {})
            if "enabled" in listen:
                return bool(listen["enabled"])
        except Exception:
            pass  # documente ci-dessus : toute erreur de lecture = on garde l'etat courant
        return bool(self.enable_voice_listen)

    async def _voice_supervisor(self):
        """Connecte/déconnecte le client d'écoute micro selon le toggle du dashboard,
        relu toutes les 15 s. Permet d'activer/désactiver l'écoute SANS redémarrer le bot."""
        inner = None
        try:
            while not self._stopped:
                desired = self._desired_voice_listen()
                running = inner is not None and not inner.done()
                if desired and not running:
                    self.logger.info(f"🎙️ [TWITCH_CHAT:{self.bot_id}] Écoute micro ACTIVÉE (dashboard).")
                    inner = asyncio.create_task(self._start_voice_listen())
                elif not desired and running:
                    self.logger.info(f"🎙️ [TWITCH_CHAT:{self.bot_id}] Écoute micro DÉSACTIVÉE (dashboard).")
                    inner.cancel()
                    try:
                        await inner
                    except asyncio.CancelledError:
                        pass  # annulation attendue : c'est nous qui venons d'appeler cancel()
                    inner = None
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            pass  # annulation attendue de la boucle elle-meme
        finally:
            if inner is not None and not inner.done():
                inner.cancel()

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
