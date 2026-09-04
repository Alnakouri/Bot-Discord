# -*- coding: utf-8 -*-
import os
import re
import json
from datetime import datetime
from pathlib import Path
from shared.twitch.sanitize import strip_stage_directions

DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent.parent.parent / "data"))

TWITCH_NAMED_COLORS = [
    "blue", "blue_violet", "cadet_blue", "chocolate", "coral",
    "dodger_blue", "firebrick", "golden_rod", "green", "hot_pink",
    "orange_red", "red", "sea_green", "spring_green", "yellow_green",
]

class DailyProfileMixin:
    def _load_profile_state(self) -> dict | None:
        path = os.path.join(DATA_DIR, f"twitch_profile_{self.bot_id}.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur lecture profil JSON: {e}")
        return None

    def _save_profile_state(self, state: dict):
        path = os.path.join(DATA_DIR, f"twitch_profile_{self.bot_id}.json")
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp_path, path)
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Échec sauvegarde profil JSON: {e}")

    async def _generate_daily_profile(self) -> tuple[str, str]:
        """
        Génère un profil Twitch autonome (bio + couleur) adapté à la personnalité du bot.
        Utilise la cascade LLM pour n'effectuer qu'un seul appel par jour.
        """
        fallback_bio = self.profile_bio or ""
        fallback_color = self.chat_color or "blue_violet"

        if not self.key_manager:
            return fallback_bio, fallback_color

        # Prompt système
        system_prompt = self.personality_prompt
        if self.system_prompt_provider:
            try:
                sp = self.system_prompt_provider()
                if sp:
                    system_prompt = sp
            except Exception as e:
                self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] system_prompt_provider a échoué dans la génération de profil : {e}")

        if not system_prompt:
            return fallback_bio, fallback_color

        persona_name = self.bot_label or self.bot_id
        prompt = (
            f"Tu es {persona_name}. Choisis ta bio de chaîne Twitch et ta couleur de pseudo pour "
            f"aujourd'hui, fidèles à ta personnalité. Réponds UNIQUEMENT par un JSON :\n"
            f'{{"bio": "<1-2 phrases, 1re personne, en personnage, ≤280 caractères, sans guillemets ni didascalies>", '
            f'"color": "<un nom EXACT parmi: blue, blue_violet, cadet_blue, chocolate, coral, '
            f'dodger_blue, firebrick, golden_rod, green, hot_pink, orange_red, red, sea_green, spring_green, yellow_green>"}}'
        )

        try:
            from shared.llm_cascade import generate_response
            from shared.smart_router import classify_request
        except ImportError as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Modules LLM indisponibles : {e}")
            return fallback_bio, fallback_color

        # On simule un routage standard (ex: text classique)
        try:
            routing = classify_request(prompt)
        except Exception:
            routing = {"type": "text"}

        try:
            text = await generate_response(
                routing=routing,
                system_prompt=system_prompt,
                transcript="",
                user_message=prompt,
                conversation_history=[],
                media_data=None,
                mime_type="",
                key_manager=self.key_manager,
                mistral_client=self.mistral_client,
                groq_client=self.groq_client,
                openrouter_client=self.openrouter_client, nvidia_client=getattr(self, "nvidia_client", None),
                bot_label=self.bot_label or self.bot_id,
                temperature=0.9,
                max_tokens=120
            )

            if text:
                text = text.strip()
                # Extraction du JSON par regex s'il y a du blabla autour
                match = re.search(r"\{.*\}", text, re.DOTALL)
                json_str = match.group(0) if match else text

                bio = ""
                color = ""
                try:
                    profile_data = json.loads(json_str)
                    bio = profile_data.get("bio", "").strip()
                    color = profile_data.get("color", "").strip().lower()
                except Exception:
                    # Parsing regex de secours
                    bio_match = re.search(r'"bio"\s*:\s*"([^"]+)"', json_str)
                    color_match = re.search(r'"color"\s*:\s*"([^"]+)"', json_str)
                    if bio_match:
                        bio = bio_match.group(1).strip()
                    if color_match:
                        color = color_match.group(1).strip().lower()

                # Nettoyage et validation de la bio
                if bio:
                    bio = strip_stage_directions(bio)
                    if (bio.startswith('"') and bio.endswith('"')) or (bio.startswith("'") and bio.endswith("'")):
                        bio = bio[1:-1].strip()
                    bio = bio[:300]
                else:
                    bio = fallback_bio

                # Validation de la couleur
                if color not in TWITCH_NAMED_COLORS:
                    self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] Couleur générée '{color}' invalide, fallback.")
                    color = fallback_color

                return bio, color
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Exception lors de la génération du profil LLM : {e}")

        return fallback_bio, fallback_color

    async def _ensure_daily_profile(self):
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Si on a déjà appliqué le profil pour "today" dans ce process, on ne fait rien pour ne pas spammer Helix
            if self._profile_day == today:
                return

            state = self._load_profile_state()
            bio, color = None, None

            if state and state.get("date") == today:
                bio = state.get("bio")
                color = state.get("color")
                self.logger.info(f"💾 [TWITCH_CHAT:{self.bot_id}] Profil du jour récupéré depuis l'état persistant (pas d'appel LLM) : bio='{bio}', color='{color}'")
            else:
                self.logger.info(f"🧠 [TWITCH_CHAT:{self.bot_id}] Aucun profil pour aujourd'hui ({today}). Génération via LLM...")
                bio, color = await self._generate_daily_profile()
                self._save_profile_state({"date": today, "bio": bio, "color": color})
                self.logger.info(f"💾 [TWITCH_CHAT:{self.bot_id}] Profil du jour sauvegardé dans l'état persistant : bio='{bio}', color='{color}'")

            # Application du profil
            if self.profile_helper:
                await self.profile_helper.update_profile(bio=bio, chat_color=color)
                self._profile_day = today
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Exception dans _ensure_daily_profile : {e}", exc_info=True)
