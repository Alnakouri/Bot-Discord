# -*- coding: utf-8 -*-
"""
shared/twitch_chat.py — Connexion permanente et chat Twitch pour les bots.
"""

import os
import re
import time
import json
import asyncio
import logging
import collections
from pathlib import Path
import aiohttp

# Path configuration
DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))

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


class TwitchChatBot:
    """
    Gère la connexion permanente IRC au chat Twitch, écoute les messages et y répond en personnage.
    """
    PRIVMSG_RE = re.compile(r"^(?:@\S+ )?:(?P<user>[^!]+)![^ ]+ PRIVMSG #(?P<chan>[^ ]+) :(?P<msg>.*)$")

    def __init__(
        self,
        bot_id: str,
        logger,
        username: str,
        channels: list[str],
        client_id: str,
        client_secret: str,
        auth: TwitchAuth,
        personality_prompt: str | None = None,
        key_manager = None,
        mistral_client = None,
        groq_client = None,
        openrouter_client = None,
        bot_label: str | None = None,
        system_prompt_provider = None
    ):
        self.bot_id = bot_id
        self.logger = logger
        self.username = username
        self.channels = channels
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth = auth
        self.personality_prompt = personality_prompt
        # Optionnel : callable renvoyant le prompt système "vivant" (ex. humeur courante
        # côté Discord). Permet d'utiliser la MÊME config que le bot principal.
        self.system_prompt_provider = system_prompt_provider
        self.key_manager = key_manager
        self.mistral_client = mistral_client
        self.groq_client = groq_client
        self.openrouter_client = openrouter_client
        self.bot_label = bot_label

        self._stopped = False
        self.histories = {}  # (channel, user) -> deque(maxlen=6)
        self.user_cooldowns = {}  # user -> float (timestamp)
        self.global_msg_timestamps = collections.deque()  # deque of floats

        # Build triggers
        trigger_terms = [username.lower(), bot_id.lower()]
        if bot_label:
            trigger_terms.append(bot_label.lower())
        
        # Add common short names for bots
        for short in ["sheo", "maiq", "johnny", "onizuka", "malena", "alfred"]:
            if short in bot_id.lower():
                trigger_terms.append(short)

        trigger_terms = sorted(list(set(t.strip().lower() for t in trigger_terms if t)), key=len, reverse=True)
        trigger_pattern = r"(?:@?(" + "|".join(re.escape(t) for t in trigger_terms) + r"))\b"
        self.trigger_re = re.compile(trigger_pattern, re.IGNORECASE)
        self.logger.info(f"🎯 [TWITCH_CHAT:{self.bot_id}] Déclencheurs configurés : {trigger_terms}")

    async def run(self):
        self._stopped = False
        backoff = 1
        
        # Démarre la boucle de refresh proactif
        refresh_task = asyncio.create_task(self._token_refresh_loop())

        try:
            while not self._stopped:
                try:
                    token = await self.auth.get_valid_token()
                    if not token:
                        self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Impossible de récupérer un token. Réessai dans {backoff}s...")
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 60)
                        continue

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
            self.logger.info(f"👋 [TWITCH_CHAT:{self.bot_id}] Arrêt de la boucle Twitch Chat.")

    async def _token_refresh_loop(self):
        while not self._stopped:
            try:
                await asyncio.sleep(60)
                now = time.time()
                if self.auth.expires_at and (self.auth.expires_at - now < 1800):
                    self.logger.info(f"🔄 [TWITCH_CHAT:{self.bot_id}] Token proche de l'expiration. Refresh proactif...")
                    await self.auth.refresh()
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

                        m = self.PRIVMSG_RE.match(line)
                        if not m:
                            continue

                        author = m.group("user")
                        chan = m.group("chan")
                        text = m.group("msg").strip()

                        # Anti-boucle
                        if author.lower() == self.username.lower():
                            continue

                        # Éviter les autres bots connus
                        known_bots = {
                            "compte_bot_sheo", "maiq_bot", "johnny_bot_discord", 
                            "onizuka_bot_discord", "malena_bot_discord", "alfred_bot_discord",
                            "nightbot", "streamelements", "wizebot", "moobot"
                        }
                        if author.lower() in known_bots:
                            continue

                        # Vérification mot déclencheur
                        if not self.trigger_re.search(text):
                            continue

                        # Cooldown par utilisateur (3s)
                        now = time.time()
                        last_user_time = self.user_cooldowns.get(author.lower(), 0)
                        if now - last_user_time < 3.0:
                            self.logger.info(f"⏳ [TWITCH_CHAT:{self.bot_id}] Message de {author} ignoré (cooldown)")
                            continue
                        self.user_cooldowns[author.lower()] = now

                        # Rate limit global (18 msgs / 30s)
                        while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
                            self.global_msg_timestamps.popleft()

                        if len(self.global_msg_timestamps) >= 18:
                            self.logger.warning(f"🚨 [TWITCH_CHAT:{self.bot_id}] Rate limit global atteint. Message ignoré.")
                            continue

                        self.logger.info(f"📥 [TWITCH_CHAT:{self.bot_id}] Message reçu de {author} sur #{chan} : {text}")

                        # Réponse
                        reply = await self._generate_response(chan, author, text)
                        if reply:
                            self.global_msg_timestamps.append(time.time())
                            await ws.send_str(f"PRIVMSG #{chan.lower()} :{reply}")
                            self.logger.info(f"📤 [TWITCH_CHAT:{self.bot_id}] Envoyé sur #{chan} : {reply}")

    async def _generate_response(self, channel: str, author: str, message: str) -> str | None:
        # Prompt système : on privilégie le provider "vivant" (même config que le bot
        # principal, ex. humeur Discord courante) ; sinon le prompt statique.
        system_prompt = self.personality_prompt
        if self.system_prompt_provider:
            try:
                sp = self.system_prompt_provider()
                if sp:
                    system_prompt = sp
            except Exception as e:
                self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] system_prompt_provider a échoué : {e}")

        if not system_prompt or self.key_manager is None:
            return None
        try:
            from shared.llm_cascade import generate_response
            from shared.smart_router import classify_request
        except ImportError as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Modules LLM indisponibles : {e}")
            return None

        history_key = (channel.lower(), author.lower())
        if history_key not in self.histories:
            self.histories[history_key] = collections.deque(maxlen=6)

        history_deque = self.histories[history_key]
        conversation_history = list(history_deque)

        # MÊME routage que Discord : classify_request choisit le modèle selon le contenu
        # (humour → Grok, raisonnement → Gemini, sinon cascade économique).
        routing = classify_request(message)

        try:
            text = await generate_response(
                routing=routing,
                system_prompt=system_prompt,
                transcript="",
                user_message=f"{author} (sur Twitch) dit : {message}",
                conversation_history=conversation_history,
                media_data=None,
                mime_type="",
                key_manager=self.key_manager,
                mistral_client=self.mistral_client,
                groq_client=self.groq_client,
                openrouter_client=self.openrouter_client,
                bot_label=self.bot_label or self.bot_id,
                temperature=1.0,
                max_tokens=120
            )
            if text:
                text = " ".join(text.split())
                text = self._strip_stage_directions(text)
                reply = text[:480]
                
                # Mise à jour historique
                history_deque.append({"role": "user", "parts": [message]})
                history_deque.append({"role": "assistant", "parts": [reply]})
                
                return reply
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur lors de la génération : {e}")
        return None

    @staticmethod
    def _strip_stage_directions(text: str) -> str:
        """Retire les didascalies de roleplay (*il se redresse...*) tout en gardant
        l'emphase (*panache* → panache). Les marqueurs `*` ne sont de toute façon
        pas rendus par Twitch."""
        # 1. Didascalie en tête de message : "*Il se redresse...* Ah..."
        text = re.sub(r"^\s*\*[^*]+\*\s*", "", text)
        # 2. Didascalie multi-mots juste après une fin de phrase : "... ! *rit doucement* Et..."
        text = re.sub(r"(?<=[.!?…])\s*\*[^*]+\s[^*]+\*\s*", " ", text)
        # 3. Le reste des astérisques = simple emphase → on retire seulement les marqueurs
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        return re.sub(r"\s{2,}", " ", text).strip()

    def stop(self):
        self._stopped = True


def setup_twitch_chat(bot_id: str, logger, *, personality_prompt: str | None = None,
                      key_manager=None, mistral_client=None, groq_client=None,
                      openrouter_client=None, bot_label: str | None = None,
                      system_prompt_provider=None) -> TwitchChatBot | None:
    """
    Initialise TwitchChatBot si les crédentiels d'environnement requis sont définis.
    """
    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")
    username = os.getenv("TWITCH_BOT_USERNAME")
    channels_csv = os.getenv("TWITCH_CHAT_CHANNELS")
    default_token = os.getenv("TWITCH_OAUTH_TOKEN")
    default_refresh = os.getenv("TWITCH_REFRESH_TOKEN")

    if not client_id or not client_secret or not username or not channels_csv or not default_token:
        logger.info(f"📡 [TWITCH_CHAT:{bot_id}] Module chat non activé (crédentiels/variables d'env manquants)")
        return None

    channels = [c.strip().lower().lstrip("#") for c in channels_csv.split(",") if c.strip()]
    if not channels:
        logger.info(f"📡 [TWITCH_CHAT:{bot_id}] Aucun canal Twitch configuré (TWITCH_CHAT_CHANNELS vide)")
        return None

    auth = TwitchAuth(bot_id, logger, client_id, client_secret, default_token, default_refresh)

    return TwitchChatBot(
        bot_id=bot_id,
        logger=logger,
        username=username,
        channels=channels,
        client_id=client_id,
        client_secret=client_secret,
        auth=auth,
        personality_prompt=personality_prompt,
        key_manager=key_manager,
        mistral_client=mistral_client,
        groq_client=groq_client,
        openrouter_client=openrouter_client,
        bot_label=bot_label,
        system_prompt_provider=system_prompt_provider
    )
