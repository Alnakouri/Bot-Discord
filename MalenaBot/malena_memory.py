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
Système de mémoire pour Malena.
- MalenaMemory : mémoire journalière (reset chaque jour)
  Basé sur le modèle DailyMemory de Sheogorath.
"""
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger("malena")


class MalenaMemory:
    def __init__(self, filename=os.path.join(DATA_DIR, "malena_memory.json")):
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
            json.dump(self.memory, f, indent=4, ensure_ascii=False)

    def check_reset(self):
        today = str(datetime.now().date())
        if self.memory.get("date") != today:
            logger.info("🌅 Nouveau jour à Marseille ! Malena oublie les dramas d'hier.")
            self.memory = {"date": today, "users": {}, "conversations": []}
            self.save_memory()

    def add_interaction(self, user_id, user_name, content, bot_response=None):
        """Enregistre une interaction utilisateur."""
        self.check_reset()
        uid = str(user_id)
        if uid not in self.memory["users"]:
            self.memory["users"][uid] = {"name": user_name, "interactions": 0, "topics": []}

        self.memory["users"][uid]["interactions"] += 1

        # Extraire des sujets potentiels (heuristique basique)
        words = content.lower().split()
        if len(words) > 3:
            topic_snippet = " ".join(words[:6])
            self.memory["users"][uid]["topics"].append(topic_snippet)
            self.memory["users"][uid]["topics"] = self.memory["users"][uid]["topics"][-5:]

        entry = {
            "time": datetime.now().strftime("%H:%M"),
            "user": user_name,
            "content": content[:100],  # Tronquer les longs messages
            "response": bot_response[:100] if bot_response else None
        }
        self.memory["conversations"].append(entry)
        # Garder les 40 dernières conversations
        if len(self.memory["conversations"]) > 40:
            self.memory["conversations"].pop(0)

        self.save_memory()

    def get_context_summary(self, user_id):
        """Retourne un résumé du contexte pour enrichir le prompt."""
        uid = str(user_id)
        users = self.memory["users"]
        summary = ""

        if uid in users:
            u_data = users[uid]
            count = u_data['interactions']
            if count > 1:
                summary += f"\n[MÉMOIRE] Tu as déjà parlé {count} fois avec cette personne aujourd'hui."
                if u_data['topics']:
                    summary += f" Sujets abordés : {', '.join(u_data['topics'][-3:])}."

        # Ajouter les 3 derniers échanges pour le contexte conversationnel
        recent_chats = self.memory["conversations"][-3:]
        if recent_chats:
            summary += "\n[CONVERSATION RÉCENTE] " + " | ".join(
                [f"{c['user']}: {c['content']}" for c in recent_chats]
            )

        return summary

    def get_user_count(self):
        """Retourne le nombre d'utilisateurs uniques aujourd'hui."""
        return len(self.memory["users"])
