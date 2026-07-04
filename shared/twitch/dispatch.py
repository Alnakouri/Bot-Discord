# -*- coding: utf-8 -*-
import time
import random
import collections
import asyncio
from datetime import datetime
from shared.twitch.sanitize import strip_stage_directions, send_chat_safe
from shared.twitch.llm import ANTI_INJECTION_GUARD

class DispatchMixin:
    async def _fetch_game_facts_block(self, chan: str, category: str):
        """Récupère un bloc de faits IGDB pour le jeu en cours sur `chan`.

        Réutilise des clients Helix/IGDB persistés sur le bot (token OAuth conservé
        entre les appels). Retourne (facts_block | None, no_facts_warning: bool).
        Toute erreur réseau → (None, True) : le bot nuance en personnage.
        """
        from shared.twitch.game_info import HelixClient, IGDBClient, get_game_facts, format_facts_block
        if getattr(self, "_helix_client", None) is None:
            self._helix_client = HelixClient(self.client_id, self.client_secret)
        if getattr(self, "_igdb_client", None) is None:
            self._igdb_client = IGDBClient(self.client_id, self.client_secret)
        try:
            game_name, _ = await self._helix_client.get_current_game(chan)
            if not game_name:
                return None, True
            facts = await get_game_facts(game_name, self.client_id, self.client_secret, igdb_client=self._igdb_client)
            if facts:
                return format_facts_block(facts, category), False
            return None, True
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur recuperation faits jeu: {e}")
            return None, True

    async def _handle_privmsg(self, chan: str, author: str, text: str, tags: dict, ws):
        # 1. Traitement des commandes bits si présents
        if "bits" in tags:
            bits_amount = tags.get("bits", "0")
            if self.enable_events:
                await self._react_to_event_with_ws(chan, "bits", {"author": author, "amount": bits_amount, "msg": text}, ws)
            return

        # 2. Check Command
        is_cmd = await self._handle_command(chan, author, text, ws)
        if is_cmd:
            return

        # 3. Check Mention
        is_mention = self.trigger_re.search(text)
        if is_mention:
            # Cooldown par utilisateur (3s)
            now = time.time()
            last_user_time = self.user_cooldowns.get(author.lower(), 0)
            if now - last_user_time < 3.0:
                self.logger.info(f"⏳ [TWITCH_CHAT:{self.bot_id}] Message de {author} ignoré (cooldown)")
                return
            self.user_cooldowns[author.lower()] = now

            # Rate limit global (18 msgs / 30s)
            while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
                self.global_msg_timestamps.popleft()

            if len(self.global_msg_timestamps) >= 18:
                self.logger.warning(f"🚨 [TWITCH_CHAT:{self.bot_id}] Rate limit global atteint. Message ignoré.")
                return

            self.logger.info(f"📥 [TWITCH_CHAT:{self.bot_id}] Message reçu de {author} sur #{chan} : {text}")

            # Le message mentionnant le bot alimente aussi le contexte ambiant du salon
            chan_key = chan.lower()
            if chan_key not in self.channel_recent:
                self.channel_recent[chan_key] = collections.deque(maxlen=8)
            self.channel_recent[chan_key].append(f"{author}: {text}")

            # On compte la tentative de génération dans le rate-limit global
            self.global_msg_timestamps.append(time.time())

            # Réponse (mention) - Réponse questions jeu
            facts_block = None
            no_facts_warning = False
            if getattr(self, "enable_game_qa", False):
                from shared.twitch.game_info import detect_game_question
                category = detect_game_question(text)
                if category:
                    facts_block, no_facts_warning = await self._fetch_game_facts_block(chan, category)

            reply = await self._generate_response(chan, author, text, game_facts_block=facts_block, no_facts_warning=no_facts_warning)
            if reply:
                await send_chat_safe(ws, chan, reply, bot_id=self.bot_id, logger=self.logger)
            return

        # 4. Message passif
        chan_lower = chan.lower()
        if chan_lower not in self.channel_recent:
            self.channel_recent[chan_lower] = collections.deque(maxlen=8)
        self.channel_recent[chan_lower].append(f"{author}: {text}")

        # Suivi des viewers (accueil)
        author_lower = author.lower()
        is_first_session_msg = False
        if author_lower not in self.session_seen:
            self.session_seen.add(author_lower)
            is_first_session_msg = True
            
            if author_lower not in self.viewers_state:
                self.viewers_state[author_lower] = {"count": 0, "last_seen": ""}
            
            today = datetime.now().strftime("%Y-%m-%d")
            viewer_data = self.viewers_state[author_lower]
            if viewer_data.get("last_seen") != today:
                viewer_data["count"] = viewer_data.get("count", 0) + 1
                viewer_data["last_seen"] = today
                self._save_viewers_state_debounced()

        # Au plus une seule action spontanée
        spontaneous_sent = False

        # Option A : Favor passif (si configuré)
        if self.passive_handler:
            try:
                if asyncio.iscoroutinefunction(self.passive_handler):
                    res = await self.passive_handler(author, text)
                else:
                    res = self.passive_handler(author, text)
                if res:
                    now = time.time()
                    while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
                        self.global_msg_timestamps.popleft()
                    if len(self.global_msg_timestamps) < 18:
                        self.global_msg_timestamps.append(now)
                        await send_chat_safe(ws, chan, res, bot_id=self.bot_id, logger=self.logger)
                        spontaneous_sent = True
            except Exception as e:
                self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur passive_handler: {e}")

        # Option A.2 : Réponse passive co-host aux questions jeu
        if not spontaneous_sent and getattr(self, "enable_game_qa", False):
            chan_key = chan.lower().lstrip("#")
            if chan_key in getattr(self, "cohost_channels", []):
                from shared.twitch.game_info import detect_game_question
                category = detect_game_question(text)
                if category:
                    now = time.time()
                    last_cohost_time = getattr(self, "_last_cohost_qa", {}).get(chan_key, 0)
                    if now - last_cohost_time >= 30.0:
                        while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
                            self.global_msg_timestamps.popleft()
                        if len(self.global_msg_timestamps) < 14:
                            facts_block, no_facts_warning = await self._fetch_game_facts_block(chan, category)

                            reply = await self._generate_response(chan, author, text, game_facts_block=facts_block, no_facts_warning=no_facts_warning)
                            if reply:
                                if not hasattr(self, "_last_cohost_qa"):
                                    self._last_cohost_qa = {}
                                self._last_cohost_qa[chan_key] = now
                                self.global_msg_timestamps.append(now)
                                await send_chat_safe(ws, chan, reply, bot_id=self.bot_id, logger=self.logger)
                                spontaneous_sent = True

        # Option B : Accueil de session
        if not spontaneous_sent and is_first_session_msg and self.enable_greetings:
            spontaneous_sent = await self._try_greeting(chan, author, ws)

        # Option C : Interjection spontanée
        if not spontaneous_sent and self.enable_interjections:
            await self._try_interjection(chan, ws)

    async def _handle_command(self, chan: str, author: str, text: str, ws) -> bool:
        if not text.startswith("!"):
            return False
            
        parts = text[1:].split(" ", 1)
        cmd_name = parts[0].strip().lower()
        args = parts[1].strip() if len(parts) > 1 else ""
        
        # Résolution alias
        if cmd_name in self.command_aliases:
            cmd_name = self.command_aliases[cmd_name]
            
        if cmd_name in self.commands:
            now = time.time()
            # Cooldown utilisateur (3s)
            last_user_time = self.user_cooldowns.get(author.lower(), 0)
            if now - last_user_time < 3.0:
                self.logger.info(f"⏳ [TWITCH_CHAT:{self.bot_id}] Commande !{cmd_name} de {author} ignorée (cooldown utilisateur)")
                return True
            self.user_cooldowns[author.lower()] = now

            # Cooldown global commande (5s)
            last_cmd_time = self.command_cooldowns.get(cmd_name, 0)
            if now - last_cmd_time < 5.0:
                self.logger.info(f"⏳ [TWITCH_CHAT:{self.bot_id}] Commande !{cmd_name} ignorée (cooldown global)")
                return True
            self.command_cooldowns[cmd_name] = now

            # Exécution
            try:
                callback = self.commands[cmd_name]
                if asyncio.iscoroutinefunction(callback):
                    res = await callback(author, args)
                else:
                    res = callback(author, args)
                
                if res:
                    while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
                        self.global_msg_timestamps.popleft()
                    
                    if len(self.global_msg_timestamps) >= 18:
                        self.logger.warning(f"🚨 [TWITCH_CHAT:{self.bot_id}] Rate limit global atteint pour la commande !{cmd_name}.")
                        return True

                    self.global_msg_timestamps.append(now)
                    await send_chat_safe(ws, chan, res, bot_id=self.bot_id, logger=self.logger)
            except Exception as e:
                self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur lors de l'exécution de la commande !{cmd_name}: {e}")
            return True
            
        return False

    async def _try_greeting(self, chan: str, author: str, ws) -> bool:
        now = time.time()
        # Cooldown accueil spécifique (15 s)
        last_greet = getattr(self, "_last_greet_ts", 0)
        if now - last_greet < 15.0:
            return False

        # Budget check (marge rate limit global)
        while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
            self.global_msg_timestamps.popleft()
        if len(self.global_msg_timestamps) >= 14:
            return False

        self._last_greet_ts = now
        self.global_msg_timestamps.append(now)

        viewer_data = self.viewers_state.get(author.lower(), {})
        count = viewer_data.get("count", 1)
        reply = self._generate_templated_greet(author, count, chan=chan)
        
        await send_chat_safe(ws, chan, reply, bot_id=self.bot_id, logger=self.logger)
        return True

    async def _try_interjection(self, chan: str, ws) -> bool:
        now = time.time()
        last_inter = getattr(self, "_last_interjection", 0)
        if now - last_inter < self.interjection_min_interval:
            return False

        if random.random() > self.interjection_chance:
            return False

        while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
            self.global_msg_timestamps.popleft()
        if len(self.global_msg_timestamps) >= 14:
            return False

        self._last_interjection = now
        self.global_msg_timestamps.append(now)

        reply = await self._generate_interjection(chan)
        if reply:
            await send_chat_safe(ws, chan, reply, bot_id=self.bot_id, logger=self.logger)
            return True
        return False

    async def _generate_interjection(self, chan: str) -> str | None:
        system_prompt = self.personality_prompt
        if self.system_prompt_provider:
            try:
                sp = self.system_prompt_provider()
                if sp:
                    system_prompt = sp
            except Exception as e:
                self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] system_prompt_provider a échoué dans _generate_interjection : {e}")

        if not system_prompt or self.key_manager is None:
            return None

        recent_msgs = list(self.channel_recent.get(chan.lower(), []))
        if not recent_msgs:
            return None

        context_str = "\n".join(recent_msgs)
        instruction = (
            f"Voici les derniers messages du chat Twitch :\n{context_str}\n\n"
            f"Fais une interjection spontanée très courte (1 phrase, max 100 caractères), en personnage, "
            f"pour commenter ou réagir avec dérision à ce que disent les viewers. Sois bref et percutant."
        )

        full_system_prompt = system_prompt + "\n\n" + ANTI_INJECTION_GUARD

        try:
            from shared.llm_cascade import generate_response
            from shared.smart_router import classify_request
            
            try:
                routing = classify_request(instruction)
            except Exception:
                routing = {"type": "text"}

            text = await generate_response(
                routing=routing,
                system_prompt=full_system_prompt,
                transcript="",
                user_message=instruction,
                conversation_history=[],
                media_data=None,
                mime_type="",
                key_manager=self.key_manager,
                mistral_client=self.mistral_client,
                groq_client=self.groq_client,
                openrouter_client=self.openrouter_client,
                bot_label=self.bot_label or self.bot_id,
                temperature=1.0,
                max_tokens=70
            )
            if text:
                text = " ".join(text.split())
                text = strip_stage_directions(text)
                return text[:480]
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur lors de l'intégration de l'interjection : {e}")
        return None
