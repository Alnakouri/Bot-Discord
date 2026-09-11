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
                    content = f.read().strip()
                # Fichier vide = aucun viewer connu encore : état NORMAL, pas une erreur.
                # `_load_viewer_facts` juste en dessous avait déjà ce garde ; celui-ci
                # l'avait manqué et criait ERROR au tableau de bord pour du nominal.
                if not content:
                    return {}
                return json.loads(content)
            except Exception as e:
                self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] Viewers JSON illisible (ignoré) : {e}")
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

    def _generate_templated_greet(self, author: str, count: int, chan: str = None) -> str:
        # Templates en personnage fournis par le bot (prioritaires, 0 LLM).
        replies = []
        if self.greeting_templates:
            key = "returning" if count >= 5 else "new"
            replies = self.greeting_templates.get(key) or self.greeting_templates.get("new") or []

        if not replies:
            # Fallbacks intégrés si le bot n'a pas défini ses propres templates
            is_sheo = "sheo" in self.bot_id.lower()
            if is_sheo:
                if count >= 5:
                    replies = [
                        "Tiens, @{author} ! Ta {count}e visite dans mes îles ? Tu y prends goût, mortel !",
                        "@{author} ! De retour pour la {count}e fois ? Haskill, range les instruments de torture, c'est un habitué !",
                        "Ah, @{author} ! La folie te réussit, c'est ta {count}e fois ici ! Prends un morceau de fromage !"
                    ]
                else:
                    replies = [
                        "@{author} vient d'entrer ! Bonjour ! Ou bonsoir ! Bref, ne touchez à rien !",
                        "Un nouveau jouet ! @{author}, bienvenue dans mon asile !",
                        "@{author} ! Quel esprit audacieux ose troubler mes îles daedriques ?",
                        "Haskill, amène le Wabbajack, nous avons un nouveau cobaye : @{author} !"
                    ]
            else:
                if count >= 5:
                    replies = [
                        "Ravi de te revoir, @{author} ! Merci pour ta fidélité ({count}e visite) !",
                        "Content de te revoir, @{author} ! Bienvenue sur le stream pour ta {count}e visite !",
                        "Hé @{author} ! Déjà {count} visites ? Tu fais quasiment partie du décor maintenant !",
                        "De retour, @{author} ? Toujours un plaisir de t'accueillir pour ta {count}e session !"
                    ]
                else:
                    replies = [
                        "Bienvenue sur le chat, @{author} !",
                        "Bonjour @{author}, ravi de t'accueillir ici !",
                        "Salutations @{author} ! Installe-toi bien et profite du spectacle !",
                        "Ah, salut @{author} ! Bienvenue parmi nous sur le chat !"
                    ]

        # Anti-répétition par canal Twitch
        if chan and replies:
            chan_key = chan.lower()
            if not hasattr(self, "_last_greet_templates"):
                self._last_greet_templates = {}
            
            last_idx = self._last_greet_templates.get(chan_key)
            choices = list(range(len(replies)))
            if last_idx is not None and len(choices) > 1 and last_idx in choices:
                choices.remove(last_idx)
            
            chosen_idx = random.choice(choices)
            self._last_greet_templates[chan_key] = chosen_idx
            template = replies[chosen_idx]
        elif replies:
            template = random.choice(replies)
        else:
            return f"Bienvenue @{author} !"

        try:
            return template.format(author=author, count=count)
        except (KeyError, IndexError, ValueError):
            return template.replace("{author}", author).replace("{count}", str(count))

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
