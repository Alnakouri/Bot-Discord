# -*- coding: utf-8 -*-
"""Statut Discord autonome : chaque bot génère son lot de statuts (présence « Regarde /
Joue / Écoute … ») À PARTIR de sa personnalité, 1×/jour, persisté (survit aux
redémarrages, 0 appel LLM le même jour). Le statut suit donc automatiquement tout
enrichissement du prompt de personnalité, exactement comme la bio (shared/discord_profile).

En cas d'échec LLM (ou module désactivé), on retombe sur la liste `fallback_activities`
fournie par le bot : le comportement reste identique à l'ancien statut codé en dur."""
import os, re, json, random, logging
from datetime import datetime

DATA_DIR = os.getenv("DATA_DIR", ".")
MAX_STATUS_LEN = 60          # un nom d'activité Discord reste court et lisible
DEFAULT_COUNT = 12           # nombre de statuts générés par jour
_TYPES = {"watching", "playing", "listening"}


class DiscordDailyStatus:
    def __init__(self, bot, bot_id, bot_label, personality_prompt,
                 fallback_activities, key_manager=None, mistral_client=None,
                 groq_client=None, openrouter_client=None,
                 system_prompt_provider=None, logger=None, enabled=True,
                 count=DEFAULT_COUNT):
        self.bot = bot
        self.bot_id = bot_id
        self.bot_label = bot_label
        self.personality_prompt = personality_prompt
        # liste de tuples (type_str, texte) — filet de sécurité si le LLM échoue
        self.fallback_activities = [
            (str(t).lower(), str(n)) for t, n in (fallback_activities or [])
            if str(t).lower() in _TYPES and str(n).strip()
        ]
        self.key_manager = key_manager
        self.mistral_client = mistral_client
        self.groq_client = groq_client
        self.openrouter_client = openrouter_client
        self.system_prompt_provider = system_prompt_provider  # optionnel: lambda -> prompt du moment
        self.logger = logger or logging.getLogger(bot_id)
        self.enabled = enabled
        self.count = count
        self._items = list(self.fallback_activities)  # statuts en vigueur
        self._loaded_day = None  # garde anti-régénération intra-process

    # --- persistance: data/discord_status_{bot_id}.json ({date, items}) ---
    def _path(self):
        return os.path.join(DATA_DIR, f"discord_status_{self.bot_id}.json")

    def _load_state(self):
        p = self._path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"❌ [DISCORD_STATUS:{self.bot_id}] lecture état: {e}")
        return None

    def _save_state(self, state):
        p = self._path(); tmp = p + ".tmp"
        try:
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, p)
        except Exception as e:
            self.logger.error(f"❌ [DISCORD_STATUS:{self.bot_id}] sauvegarde état: {e}")

    @staticmethod
    def _parse_items(text):
        """Extrait une liste [(type, texte)] d'une réponse LLM (JSON tolérant).

        Attend un tableau d'objets {"type": "watching|playing|listening", "text": "…"}.
        Robuste aux ```fences```, au texte autour et aux types en français/majuscules."""
        if not text:
            return []
        raw = text.strip()
        raw = re.sub(r"^```[a-zA-Z]*", "", raw).replace("```", "").strip()
        i, j = raw.find("["), raw.rfind("]")
        if i == -1 or j == -1 or j < i:
            return []
        try:
            data = json.loads(raw[i:j + 1])
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        alias = {
            "watch": "watching", "watching": "watching", "regarde": "watching",
            "play": "playing", "playing": "playing", "joue": "playing",
            "listen": "listening", "listening": "listening", "écoute": "listening",
            "ecoute": "listening",
        }
        out, seen = [], set()
        for it in data:
            if not isinstance(it, dict):
                continue
            t = alias.get(str(it.get("type", "")).strip().lower())
            txt = str(it.get("text", "")).strip().strip('"\'' )
            txt = re.sub(r"\s{2,}", " ", txt)
            if not t or not txt:
                continue
            txt = txt[:MAX_STATUS_LEN].rstrip()
            key = (t, txt.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append((t, txt))
        return out

    async def _generate_daily_status(self):
        """1 seul appel cascade/jour. Renvoie une liste [(type, texte)] en personnage,
        sinon [] (le bot gardera alors sa liste fallback)."""
        if not (self.enabled and self.key_manager):
            return []
        system_prompt = self.personality_prompt
        if self.system_prompt_provider:
            try:
                sp = self.system_prompt_provider()
                if sp: system_prompt = sp
            except Exception as e:
                self.logger.warning(f"⚠️ [DISCORD_STATUS:{self.bot_id}] system_prompt_provider: {e}")
        if not system_prompt:
            return []
        persona = self.bot_label or self.bot_id
        prompt = (
            f"Tu es {persona}. Génère {self.count} idées de STATUT Discord (l'activité "
            f"affichée sous ton nom), fidèles à ta personnalité et à ton univers. "
            f"Chaque statut a un type parmi \"watching\" (affiché « Regarde … »), "
            f"\"playing\" (« Joue … ») ou \"listening\" (« Écoute … ») et un texte COURT "
            f"(≤ 8 mots) grammaticalement cohérent avec ce verbe. Varie les types et les idées, "
            f"en personnage, sans guillemets ni didascalies.\n"
            f"Réponds UNIQUEMENT par un tableau JSON, ex: "
            f'[{{"type":"watching","text":"le caramel dorer"}},'
            f'{{"type":"playing","text":"à la marchande de bonbons"}},'
            f'{{"type":"listening","text":"craquer le sucre d\'orge"}}]'
        )
        try:
            from shared.llm_cascade import generate_response
            from shared.smart_router import classify_request
        except ImportError as e:
            self.logger.error(f"❌ [DISCORD_STATUS:{self.bot_id}] modules LLM indisponibles: {e}")
            return []
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
                bot_label=persona, temperature=0.9, max_tokens=400)
        except Exception as e:
            self.logger.error(f"❌ [DISCORD_STATUS:{self.bot_id}] appel LLM: {e}")
            return []
        return self._parse_items(text)

    async def ensure_daily_status(self):
        """À appeler avant chaque rotation de statut. Régénère seulement au changement
        de jour ; sinon réutilise les statuts en cache (0 appel LLM). No-op si désactivé
        (garde alors la liste fallback fournie au constructeur)."""
        if not self.enabled:
            return
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            if self._loaded_day == today and self._items:
                return
            state = self._load_state()
            if state and state.get("date") == today and state.get("items"):
                items = self._parse_items(json.dumps(
                    [{"type": t, "text": n} for t, n in state["items"]]))
                if items:
                    self._items = items
                    self._loaded_day = today
                    self.logger.info(
                        f"💾 [DISCORD_STATUS:{self.bot_id}] {len(items)} statuts du jour (cache, 0 LLM)")
                    return
            items = await self._generate_daily_status()
            if items:
                self._items = items
                self._loaded_day = today
                self._save_state({"date": today,
                                  "items": [[t, n] for t, n in items]})
                self.logger.info(
                    f"🧠 [DISCORD_STATUS:{self.bot_id}] {len(items)} nouveaux statuts générés")
            else:
                # LLM indisponible : on garde le fallback, sans marquer le jour
                self._items = self._items or list(self.fallback_activities)
        except Exception as e:
            self.logger.error(
                f"❌ [DISCORD_STATUS:{self.bot_id}] ensure_daily_status: {e}", exc_info=True)

    def pick_activity(self):
        """Renvoie un discord.Activity tiré au hasard des statuts en vigueur
        (générés du jour, ou fallback). None si vraiment aucun statut."""
        items = self._items or self.fallback_activities
        if not items:
            return None
        try:
            import discord
        except Exception:
            return None
        t, name = random.choice(items)
        act_type = getattr(discord.ActivityType, t, discord.ActivityType.playing)
        return discord.Activity(type=act_type, name=name)
