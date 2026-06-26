# -*- coding: utf-8 -*-
"""Bio Discord autonome : chaque bot choisit sa description d'application ("À propos de moi")
selon sa personnalité, 1×/jour, persistée (survit aux redémarrages, 0 appel LLM le même jour)."""
import os, re, json, logging
from datetime import datetime

DATA_DIR = os.getenv("DATA_DIR", ".")
MAX_BIO_LEN = 400  # limite Discord pour la description d'application

class DiscordDailyBio:
    def __init__(self, bot, bot_id, bot_label, personality_prompt,
                 key_manager=None, mistral_client=None, groq_client=None,
                 openrouter_client=None, system_prompt_provider=None,
                 logger=None, enabled=True):
        self.bot = bot
        self.bot_id = bot_id
        self.bot_label = bot_label
        self.personality_prompt = personality_prompt
        self.key_manager = key_manager
        self.mistral_client = mistral_client
        self.groq_client = groq_client
        self.openrouter_client = openrouter_client
        self.system_prompt_provider = system_prompt_provider  # optionnel: lambda -> prompt du moment
        self.logger = logger or logging.getLogger(bot_id)
        self.enabled = enabled
        self._applied_day = None  # garde anti-spam intra-process

    # --- persistance: data/discord_bio_{bot_id}.json ({date, bio}) ---
    def _path(self):
        return os.path.join(DATA_DIR, f"discord_bio_{self.bot_id}.json")
    def _load_state(self):
        p = self._path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f: return json.load(f)
            except Exception as e:
                self.logger.error(f"❌ [DISCORD_BIO:{self.bot_id}] lecture état: {e}")
        return None
    def _save_state(self, state):
        p = self._path(); tmp = p + ".tmp"
        try:
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f: json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, p)
        except Exception as e:
            self.logger.error(f"❌ [DISCORD_BIO:{self.bot_id}] sauvegarde état: {e}")

    @staticmethod
    def _strip_stage_directions(text):
        text = (text or "").strip()
        # déroule/retire les astérisques (italique/didascalies) SANS vider le texte
        text = re.sub(r"\*+([^*]*)\*+", r"\1", text)
        text = text.replace("*", "").strip()
        # retire un label « À propos de moi : » que certains modèles préfixent
        text = re.sub(r"^[«\"']?\s*[àa]\s+propos\s+de\s+moi\s*[:：]?\s*[»\"']?\s*",
                      "", text, flags=re.IGNORECASE)
        return re.sub(r"\s{2,}", " ", text).strip()

    async def _generate_daily_bio(self):
        """1 seul appel cascade/jour. Renvoie une bio en personnage (≤400), sinon fallback."""
        fallback = ""  # à défaut on garde la description actuelle (cf. ensure_daily_bio)
        if not (self.enabled and self.key_manager):
            return fallback
        system_prompt = self.personality_prompt
        if self.system_prompt_provider:
            try:
                sp = self.system_prompt_provider()
                if sp: system_prompt = sp
            except Exception as e:
                self.logger.warning(f"⚠️ [DISCORD_BIO:{self.bot_id}] system_prompt_provider: {e}")
        if not system_prompt:
            return fallback
        persona = self.bot_label or self.bot_id
        prompt = (
            f"Tu es {persona}. Écris ta nouvelle bio Discord (section « À propos de moi ») pour "
            f"aujourd'hui, fidèle à ta personnalité et à ton univers. Réponds UNIQUEMENT par la bio, "
            f"à la 1re personne, en personnage, 1 à 3 phrases, SANS guillemets ni didascalies, "
            f"≤ 280 caractères."
        )
        try:
            from shared.llm_cascade import generate_response
            from shared.smart_router import classify_request
        except ImportError as e:
            self.logger.error(f"❌ [DISCORD_BIO:{self.bot_id}] modules LLM indisponibles: {e}")
            return fallback
        try:
            routing = classify_request(prompt)
        except Exception:
            routing = {"type": "text"}
        try:
            text = await generate_response(
                routing=routing, system_prompt=system_prompt, transcript="",
                user_message=prompt, conversation_history=[], media_data=None, mime_type="",
                key_manager=self.key_manager, mistral_client=self.mistral_client,
                groq_client=self.groq_client, openrouter_client=self.openrouter_client,
                bot_label=persona, temperature=0.9, max_tokens=160)
        except Exception as e:
            self.logger.error(f"❌ [DISCORD_BIO:{self.bot_id}] appel LLM: {e}")
            return fallback
        if not text:
            return fallback
        bio = self._strip_stage_directions(text.strip())
        if (bio.startswith('"') and bio.endswith('"')) or (bio.startswith("'") and bio.endswith("'")):
            bio = bio[1:-1].strip()
        return bio[:MAX_BIO_LEN]

    async def ensure_daily_bio(self):
        """À appeler au démarrage + 1×/h. Régénère seulement au changement de jour ;
        sinon ré-applique la bio stockée (0 appel LLM). No-op si désactivé."""
        if not self.enabled:
            return
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            if self._applied_day == today:
                return
            state = self._load_state()
            if state and state.get("date") == today and state.get("bio"):
                bio = state["bio"]
                self.logger.info(f"💾 [DISCORD_BIO:{self.bot_id}] bio du jour (cache, 0 LLM): {bio!r}")
            else:
                bio = await self._generate_daily_bio()
                if bio:
                    self._save_state({"date": today, "bio": bio})
                    self.logger.info(f"🧠 [DISCORD_BIO:{self.bot_id}] nouvelle bio générée: {bio!r}")
            if bio:
                app = await self.bot.application_info()
                await app.edit(description=bio)
                self._applied_day = today
                self.logger.info(f"✅ [DISCORD_BIO:{self.bot_id}] « À propos de moi » mis à jour.")
        except Exception as e:
            self.logger.error(f"❌ [DISCORD_BIO:{self.bot_id}] ensure_daily_bio: {e}", exc_info=True)
