# -*- coding: utf-8 -*-
import asyncio
import time
from shared.twitch.sanitize import strip_stage_directions, send_chat_safe
from shared.twitch.llm import ANTI_INJECTION_GUARD

class VoiceMixin:
    async def _start_voice_listen(self):
        try:
            from shared.stream_listener import StreamListenerClient
        except ImportError as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Module StreamListenerClient non disponible: {e}")
            return

        self.logger.info(f"🎙️ [TWITCH_CHAT:{self.bot_id}] Initialisation de l'écoute continu...")
        
        self.voice_client = StreamListenerClient(
            bot_id=self.bot_id,
            logger=self.logger,
            on_transcript_received_callback=self._on_voice_transcript,
            port=self.listen_port,
            host=self.listen_host
        )
        try:
            await self.voice_client.run()
        except asyncio.CancelledError:
            self.voice_client.stop()
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur dans la tâche d'écoute voix : {e}")
        finally:
            self.voice_client = None

    async def _on_voice_transcript(self, text: str, text_hash: str):
        if not text or not self.channels:
            return
            
        words = text.split()
        if len(words) < 3:
            return
            
        now = time.time()
        if now - self._last_voice_ts < self.voice_min_interval:
            self.logger.info(f"🎙️ [TWITCH_CHAT:{self.bot_id}] Énoncé voix drop (intervalle de {self.voice_min_interval}s non écoulé)")
            return
            
        # Le bot ne réagit à la voix QUE si l'un de ses noms est prononcé (décision produit).
        if not self.trigger_re.search(text):
            return
            
        if not hasattr(self, "voice_client") or not self.voice_client:
            return
            
        granted = await self.voice_client.request_claim(text_hash)
        if not granted:
            self.logger.info(f"🎙️ [TWITCH_CHAT:{self.bot_id}] Claim refusé par le hub (déjà pris).")
            return
            
        while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
            self.global_msg_timestamps.popleft()
        if len(self.global_msg_timestamps) >= 18:
            self.logger.warning(f"🚨 [TWITCH_CHAT:{self.bot_id}] Écoute voix: rate limit global atteint (18/30s). Message ignoré.")
            return
            
        chan = self.channels[0]
        reply = await self._generate_voice_response(text)
        if reply:
            self.global_msg_timestamps.append(now)
            await send_chat_safe(self.ws, chan, reply, bot_id=self.bot_id, logger=self.logger)
            self._last_voice_ts = now

    async def _generate_voice_response(self, text: str) -> str | None:
        system_prompt = self.personality_prompt
        if self.system_prompt_provider:
            try:
                sp = self.system_prompt_provider()
                if sp:
                    system_prompt = sp
            except Exception as e:
                self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] system_prompt_provider a échoué dans _generate_voice_response : {e}")

        if not system_prompt or self.key_manager is None:
            return None

        instruction = (
            f"Le streamer vient de dire en direct au micro :\n\"{text}\"\n\n"
            f"Fais une réponse très courte (1 phrase, max 100 caractères), en personnage, "
            f"pour commenter ou réagir avec dérision/humour à ce que vient de dire le streamer. Sois bref et percutant."
        )

        full_system_prompt = system_prompt + "\n\n" + ANTI_INJECTION_GUARD

        if getattr(self, "tone_directive_provider", None):
            try:
                td = self.tone_directive_provider("", text)
                if td:
                    full_system_prompt += td
            except Exception as e:
                self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] tone_directive_provider a échoué (voix) : {e}")

        try:
            from shared.llm_cascade import generate_response
            from shared.smart_router import classify_request
            
            try:
                routing = classify_request(instruction)
            except Exception:
                routing = {"type": "text"}

            reply = await generate_response(
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
                openrouter_client=self.openrouter_client, nvidia_client=getattr(self, "nvidia_client", None),
                bot_label=self.bot_label or self.bot_id,
                temperature=1.0,
                max_tokens=60
            )
            if reply:
                reply = " ".join(reply.split())
                reply = strip_stage_directions(reply)
                return reply[:480]
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur lors de la génération de la réponse voix: {e}")
        return None
