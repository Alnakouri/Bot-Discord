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


def _legacy_to_text(type_str, text):
    """Convertit un type et texte d'activité hérités (watching/playing/listening)
    en une phrase autonome (Regarde {texte}, Joue {texte}, Écoute {texte}) tronquée."""
    alias = {
        "watch": "watching", "watching": "watching", "regarde": "watching",
        "play": "playing", "playing": "playing", "joue": "playing",
        "listen": "listening", "listening": "listening", "écoute": "listening",
        "ecoute": "listening",
    }
    t = alias.get(str(type_str).strip().lower())
    txt = str(text).strip().strip('"\'' )
    if not t or not txt:
        return ""
    if t == "watching":
        res = f"Regarde {txt}"
    elif t == "playing":
        res = f"Joue {txt}"
    elif t == "listening":
        res = f"Écoute {txt}"
    else:
        return ""
    # Nettoyer les espaces multiples
    res = re.sub(r"\s{2,}", " ", res).strip()
    return res[:MAX_STATUS_LEN]


class DiscordDailyStatus:
    def __init__(self, bot, bot_id, bot_label, personality_prompt,
                 fallback_activities, key_manager=None, mistral_client=None,
                 groq_client=None, openrouter_client=None, nvidia_client=None,
                 system_prompt_provider=None, logger=None, enabled=True,
                 count=DEFAULT_COUNT):
        self.bot = bot
        self.bot_id = bot_id
        self.bot_label = bot_label
        self.personality_prompt = personality_prompt
        
        # conversion des fallbacks en phrases autonomes
        seen = set()
        self.fallback_activities = []
        for t, n in (fallback_activities or []):
            txt = _legacy_to_text(t, n)
            if txt:
                k = txt.lower()
                if k not in seen:
                    seen.add(k)
                    self.fallback_activities.append(txt)

        self.key_manager = key_manager
        self.mistral_client = mistral_client
        self.groq_client = groq_client
        self.openrouter_client = openrouter_client
        self.nvidia_client = nvidia_client
        self.system_prompt_provider = system_prompt_provider  # optionnel: lambda -> prompt du moment
        self.logger = logger or logging.getLogger(bot_id)
        self.enabled = enabled
        self.count = count
        self._items = list(self.fallback_activities)  # statuts en vigueur (liste de str)
        self._loaded_day = None  # garde anti-régénération intra-process

    # --- persistance: data/discord_status_{bot_id}.json ({date, texts}) ---
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
        """Extrait une liste de chaînes (statuts personnalisés) d'une réponse LLM (JSON tolérant).

        Gère soit un tableau de chaînes, soit un tableau d'objets (ancien format).
        Robuste aux ```fences```, au texte autour et aux types en français/majuscules.
        """
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

        out, seen = [], set()
        for it in data:
            if isinstance(it, str):
                txt = it.strip().strip('"\'' )
                txt = re.sub(r"\s{2,}", " ", txt).strip()
                if not txt:
                    continue
                txt = txt[:MAX_STATUS_LEN].rstrip()
                key = txt.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(txt)
            elif isinstance(it, dict):
                t = it.get("type", "")
                val = it.get("text", "")
                txt = _legacy_to_text(t, val)
                if not txt:
                    continue
                key = txt.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(txt)
        return out

    async def _generate_daily_status(self):
        """1 seul appel cascade/jour. Renvoie une liste de str en personnage,
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
            f"Tu es {persona}. Génère {self.count} propositions de STATUTS personnalisés "
            f"Discord, courts (≤ 8 mots) et autonomes (lisibles seuls, sans verbe imposé/sous-entendu), "
            f"fidèles à ta personnalité et à ton univers. "
            f"Écris-les directement en personnage, sans guillemets ni didascalies. Un emoji de ton optionnel en fin.\n"
            f"Réponds UNIQUEMENT par un tableau JSON de chaînes, ex: "
            f'["Je fais fondre le caramel 🍬", "Recrutement de bonbons rebelles", "Le sucre d\'orge craque encore"]'
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
                groq_client=self.groq_client, openrouter_client=self.openrouter_client, nvidia_client=getattr(self, "nvidia_client", None),
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
            if state and state.get("date") == today:
                if "texts" in state and isinstance(state["texts"], list):
                    self._items = [t[:MAX_STATUS_LEN] for t in state["texts"] if isinstance(t, str) and t.strip()]
                    self._loaded_day = today
                    self.logger.info(
                        f"💾 [DISCORD_STATUS:{self.bot_id}] {len(self._items)} statuts du jour (cache, 0 LLM)")
                    return
                elif "items" in state and isinstance(state["items"], list):
                    converted = []
                    for item in state["items"]:
                        if isinstance(item, list) and len(item) == 2:
                            t, n = item[0], item[1]
                        elif isinstance(item, dict):
                            t, n = item.get("type"), item.get("text")
                        else:
                            continue
                        txt = _legacy_to_text(t, n)
                        if txt:
                            converted.append(txt)
                    seen = set()
                    deduped = []
                    for txt in converted:
                        k = txt.lower()
                        if k not in seen:
                            seen.add(k)
                            deduped.append(txt)
                    if deduped:
                        self._items = deduped
                        self._loaded_day = today
                        self.logger.info(
                            f"💾 [DISCORD_STATUS:{self.bot_id}] {len(deduped)} statuts du jour (cache migré, 0 LLM)")
                        return
            items = await self._generate_daily_status()
            if items:
                self._items = items
                self._loaded_day = today
                self._save_state({"date": today, "texts": items})
                self.logger.info(
                    f"🧠 [DISCORD_STATUS:{self.bot_id}] {len(items)} nouveaux statuts générés")
            else:
                # LLM indisponible : on garde le fallback, sans marquer le jour
                self._items = self._items or list(self.fallback_activities)
        except Exception as e:
            self.logger.error(
                f"❌ [DISCORD_STATUS:{self.bot_id}] ensure_daily_status: {e}", exc_info=True)

    def pick_activity(self):
        """Renvoie un discord.CustomActivity tiré au hasard des statuts en vigueur
        (générés du jour, ou fallback). None si vraiment aucun statut."""
        items = self._items or self.fallback_activities
        if not items:
            return None
        try:
            import discord
        except Exception:
            return None
        texte = random.choice(items)
        return discord.CustomActivity(name=texte)
