import os
DATA_DIR = os.getenv("DATA_DIR", ".")
# -*- coding: utf-8 -*-

# INJECTION SHARED FOLDER
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

"""
Système de mémoire pour Sheogorath.
- DailyMemory : mémoire journalière (reset chaque jour)
- FactMemory : mémoire persistante des faits appris sur les utilisateurs
"""
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger("sheogorath")


class DailyMemory:
    def __init__(self, filename=os.path.join(DATA_DIR, "sheogorath_memory.json")):
        self.filename = filename
        self.memory = self.load_memory()
        self.check_reset()

    def load_memory(self):
        if not os.path.exists(self.filename):
            return {"date": str(datetime.now().date()), "users": {}, "conversations": []}
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Erreur chargement mémoire: {e}")
            return {"date": str(datetime.now().date()), "users": {}, "conversations": []}

    def save_memory(self):
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, indent=4)

    def check_reset(self):
        today = str(datetime.now().date())
        if self.memory.get("date") != today:
            logger.info("🌅 Une nouvelle journée commence aux Îles Trémensides ! Mémoire effacée.")
            self.memory = {"date": today, "users": {}, "conversations": []}
            self.save_memory()

    def add_interaction(self, user_id, user_name, content, bot_response=None):
        self.check_reset()
        uid = str(user_id)
        if uid not in self.memory["users"]:
            self.memory["users"][uid] = {"name": user_name, "interactions": 0, "topics": []}

        self.memory["users"][uid]["interactions"] += 1
        # Extract potential topics (basic heuristic)
        words = content.split()
        if len(words) > 3:
            topic_snippet = " ".join(words[:5]) + "..."
            self.memory["users"][uid]["topics"].append(topic_snippet)
            self.memory["users"][uid]["topics"] = self.memory["users"][uid]["topics"][-5:]

        entry = {
            "time": str(datetime.now().strftime("%H:%M")),
            "user": user_name,
            "content": content,
            "response": bot_response
        }
        self.memory["conversations"].append(entry)
        # Keep last 50 global conversations for context
        if len(self.memory["conversations"]) > 50:
            self.memory["conversations"].pop(0)

        self.save_memory()

    def get_context_summary(self, user_id):
        uid = str(user_id)
        users = self.memory["users"]
        summary = ""

        if uid in users:
            u_data = users[uid]
            summary += f"\n[MÉMOIRE JOURNÉE] Interactions aujourd'hui: {u_data['interactions']}. Sujets: {', '.join(u_data['topics'])}."

        # Add last 3 global exchanges for flow
        recent_chats = self.memory["conversations"][-3:]
        if recent_chats:
            summary += "\n[RÉCENT] " + " | ".join([f"{c['user']}: {c['content']}" for c in recent_chats])

        return summary


class FactMemory:
    def __init__(self, filename=os.path.join(DATA_DIR, "sheo_facts.json")):
        self.filename = filename
        self.facts = self.load_facts()

    def load_facts(self):
        if not os.path.exists(self.filename):
            return {}
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Erreur chargement faits: {e}")
            return {}

    def save_facts(self):
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(self.facts, f, indent=4, ensure_ascii=False)

    def get_facts(self, user_id):
        uid = str(user_id)
        return self.facts.get(uid, [])

    def add_fact(self, user_id, fact):
        uid = str(user_id)
        if uid not in self.facts:
            self.facts[uid] = []
        if fact not in self.facts[uid]:
            self.facts[uid].append(fact)
            # Limit to 10 key facts per user to avoid token explosion
            if len(self.facts[uid]) > 10:
                self.facts[uid].pop(0)
            self.save_facts()
            logger.info(f"🧠 [MEMOIRE] Fait appris sur {uid}: {fact}")
