# -*- coding: utf-8 -*-
import os
import json
import time
import random
from pathlib import Path

DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent.parent.parent / "data"))

class ViewerMemoryMixin:
    def _load_viewers_state(self) -> dict:
        path = os.path.join(DATA_DIR, f"twitch_viewers_{self.bot_id}.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Erreur lecture viewers JSON: {e}")
        return {}

    def _save_viewers_state_debounced(self):
        now = time.time()
        if now - getattr(self, "_last_viewers_save", 0) < 30.0:
            return
        self._last_viewers_save = now
        path = os.path.join(DATA_DIR, f"twitch_viewers_{self.bot_id}.json")
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.viewers_state, f, indent=2)
            os.replace(tmp_path, path)
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Échec sauvegarde viewers JSON: {e}")

    def _load_viewer_facts(self) -> dict:
        path = os.path.join(DATA_DIR, f"twitch_facts_{self.bot_id}.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                # Fichier vide = pas encore de facts : état NORMAL, pas une erreur.
                if not content:
                    return {}
                return json.loads(content)
            except Exception as e:
                self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] Facts JSON illisible (ignoré) : {e}")
        return {}

    def _save_viewer_facts_debounced(self):
        now = time.time()
        if now - getattr(self, "_last_facts_save", 0) < 30.0:
            return
        self._last_facts_save = now
        path = os.path.join(DATA_DIR, f"twitch_facts_{self.bot_id}.json")
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.viewer_facts, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception as e:
            self.logger.error(f"❌ [TWITCH_CHAT:{self.bot_id}] Échec sauvegarde facts JSON: {e}")

    def _generate_templated_greet(self, author: str, count: int) -> str:
        # Templates en personnage fournis par le bot (prioritaires, 0 LLM).
        if self.greeting_templates:
            key = "returning" if count >= 5 else "new"
            replies = self.greeting_templates.get(key) or self.greeting_templates.get("new") or []
            if replies:
                try:
                    return random.choice(replies).format(author=author, count=count)
                except (KeyError, IndexError, ValueError):
                    pass  # template malformé → repli générique ci-dessous

        is_sheo = "sheo" in self.bot_id.lower()
        if is_sheo:
            if count >= 5:
                replies = [
                    f"Tiens, @{author} ! Ta {count}e visite dans mes îles ? Tu y prends goût, mortel !",
                    f"@{author} ! De retour pour la {count}e fois ? Haskill, range les instruments de torture, c'est un habitué !",
                    f"Ah, @{author} ! La folie te réussit, c'est ta {count}e fois ici ! Prends un morceau de fromage !"
                ]
            else:
                replies = [
                    f"@{author} vient d'entrer ! Bonjour ! Ou bonsoir ! Bref, ne touchez à rien !",
                    f"Un nouveau jouet ! @{author}, bienvenue dans mon asile !",
                    f"@{author} ! Quel esprit audacieux ose troubler mes îles daedriques ?"
                ]
        else:
            if count >= 5:
                replies = [
                    f"Ravi de te revoir, @{author} ! Merci pour ta fidélité ({count}e visite) !",
                    f"Content de te revoir, @{author} ! Bienvenue sur le stream pour ta {count}e visite !"
                ]
            else:
                replies = [
                    f"Bienvenue sur le chat, @{author} !",
                    f"Bonjour @{author}, ravi de t'accueillir ici !"
                ]
        return random.choice(replies)

    async def _handle_usernotice(self, chan: str, tags: dict, msg_text: str, ws):
        msg_id = tags.get("msg-id")
        if not msg_id:
            return

        display_name = tags.get("display-name") or tags.get("login") or "Un utilisateur"
        sys_msg = tags.get("system-msg") or ""

        ctx = {
            "user": display_name,
            "sys_msg": sys_msg,
            "msg": msg_text
        }

        if msg_id in ("sub", "resub"):
            ctx["months"] = tags.get("msg-param-cumulative-months", "1")
            ctx["tier"] = tags.get("msg-param-sub-plan", "Tier 1")
            await self._react_to_event_with_ws(chan, "sub", ctx, ws)
        elif msg_id in ("subgift", "anonsubgift"):
            if "msg-param-community-gift-id" in tags:
                return
            ctx["giver"] = display_name if msg_id == "subgift" else "Un utilisateur anonyme"
            ctx["receiver"] = tags.get("msg-param-recipient-display-name") or "un viewer"
            await self._react_to_event_with_ws(chan, "subgift", ctx, ws)
        elif msg_id == "submysterygift":
            ctx["giver"] = display_name
            ctx["count"] = tags.get("msg-param-mass-gift-count", "1")
            await self._react_to_event_with_ws(chan, "submysterygift", ctx, ws)
        elif msg_id == "raid":
            ctx["raider"] = tags.get("msg-param-displayName") or display_name
            ctx["viewers"] = tags.get("msg-param-viewerCount", "0")
            await self._react_to_event_with_ws(chan, "raid", ctx, ws)
