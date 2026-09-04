# -*- coding: utf-8 -*-
import time
from shared.twitch.sanitize import strip_stage_directions, send_chat_safe
from shared.twitch.llm import ANTI_INJECTION_GUARD

class EventsMixin:
    async def _react_to_event_with_ws(self, chan: str, kind: str, ctx: dict, ws):
        now = time.time()
        while self.global_msg_timestamps and now - self.global_msg_timestamps[0] > 30.0:
            self.global_msg_timestamps.popleft()
            
        if len(self.global_msg_timestamps) >= 18:
            self.logger.warning(f"🚨 [TWITCH_CHAT:{self.bot_id}] Rate limit global atteint pour l'événement {kind}. Ignoré.")
            return

        last_event = getattr(self, "_last_event_ts", 0)
        if now - last_event < 8.0:
            self.logger.info(f"⏳ [TWITCH_CHAT:{self.bot_id}] Événement {kind} ignoré (cooldown événement)")
            return
        self._last_event_ts = now

        self.global_msg_timestamps.append(now)

        reply = await self._react_to_event(chan, kind, ctx)
        if reply:
            await send_chat_safe(ws, chan, reply, bot_id=self.bot_id, logger=self.logger)

    async def _react_to_event(self, chan: str, kind: str, ctx: dict) -> str | None:
        system_prompt = self.personality_prompt
        if self.system_prompt_provider:
            try:
                sp = self.system_prompt_provider()
                if sp:
                    system_prompt = sp
            except Exception as e:
                self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] system_prompt_provider a échoué dans _react_to_event : {e}")

        if not system_prompt or self.key_manager is None:
            return self._get_fallback_event_reply(kind, ctx)

        if kind == "sub":
            months = ctx.get("months", "1")
            tier = ctx.get("tier", "Tier 1")
            user = ctx.get("user", "Un abonné")
            sys_msg = ctx.get("sys_msg", f"{user} s'est abonné !")
            instruction = f"Réagis en tant que {self.bot_label or self.bot_id} à l'abonnement de {user} (Mois cumulés: {months}, Niveau: {tier}). Message système: \"{sys_msg}\"."
        elif kind == "subgift":
            giver = ctx.get("giver", "Un généreux donateur")
            receiver = ctx.get("receiver", "un viewer")
            instruction = f"Réagis en tant que {self.bot_label or self.bot_id} au fait que {giver} offre un abonnement à {receiver}."
        elif kind == "submysterygift":
            giver = ctx.get("giver", "Un généreux donateur")
            count = ctx.get("count", "1")
            instruction = f"Réagis en tant que {self.bot_label or self.bot_id} au fait que {giver} offre {count} abonnements à la communauté."
        elif kind == "raid":
            raider = ctx.get("raider", "Un streamer")
            viewers = ctx.get("viewers", "0")
            instruction = f"Réagis en tant que {self.bot_label or self.bot_id} au raid de {raider} avec {viewers} spectateurs !"
        elif kind == "bits":
            user = ctx.get("author", "Un spectateur")
            amount = ctx.get("amount", "0")
            msg = ctx.get("msg", "")
            instruction = f"Réagis en tant que {self.bot_label or self.bot_id} au don de {amount} bits de {user}. Message : \"{msg}\"."
        else:
            return None

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
                openrouter_client=self.openrouter_client, nvidia_client=getattr(self, "nvidia_client", None),
                bot_label=self.bot_label or self.bot_id,
                temperature=1.0,
                max_tokens=80
            )
            if text:
                text = " ".join(text.split())
                text = strip_stage_directions(text)
                return text[:480]
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur génération réaction event {kind}: {e}")

        return self._get_fallback_event_reply(kind, ctx)

    def _get_fallback_event_reply(self, kind: str, ctx: dict) -> str | None:
        is_sheo = "sheo" in self.bot_id.lower()
        if kind == "sub":
            user = ctx.get("user", "Mortel")
            if is_sheo:
                return f"Un abonnement de {user} ! Haskill, apporte le fromage de célébration ! Et plus vite que ça !"
            return f"Merci pour ton abonnement, {user} ! Bienvenue au club !"
        elif kind == "subgift":
            giver = ctx.get("giver", "Un généreux donateur")
            receiver = ctx.get("receiver", "un mortel")
            if is_sheo:
                return f"Oh ! {giver} offre un abonnement à {receiver} ! Quelle générosité folle ! J'adore !"
            return f"Merci {giver} pour le cadeau offert à {receiver} !"
        elif kind == "submysterygift":
            giver = ctx.get("giver", "Un donateur")
            count = ctx.get("count", "1")
            if is_sheo:
                return f"Incroyable ! {giver} offre {count} abonnements à la communauté ! Du fromage pour tout le monde !"
            return f"Merci {giver} pour les {count} abonnements offerts !"
        elif kind == "raid":
            raider = ctx.get("raider", "Un streamer")
            viewers = ctx.get("viewers", "0")
            if is_sheo:
                return f"Un raid de {raider} avec {viewers} spectateurs ?! Bienvenue dans mes îles ! Laissez vos cerveaux à l'entrée, vous n'en aurez pas besoin !"
            return f"Bienvenue au raid de {raider} et ses {viewers} spectateurs !"
        elif kind == "bits":
            user = ctx.get("author", "Spectateur")
            amount = ctx.get("amount", "0")
            if is_sheo:
                return f"Des morceaux de métal étincelants ! {user} me donne {amount} bits ! Haskill va les compter avec ses dents !"
            return f"Merci {user} pour les {amount} bits !"
        return None
