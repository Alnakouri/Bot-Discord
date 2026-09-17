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

MIN_DAILY_INTERACTIONS = 3
DAILY_READ_PROMPT = (
    "Tu aides un bot à AJUSTER SON TON pour aujourd'hui avec un interlocuteur. "
    "À partir des éléments fournis, donne UNE SEULE phrase courte (max ~15 mots) de consigne "
    "d'ATTITUDE/de TON à adopter avec cette personne aujourd'hui (ex: 'reste taquin et léger', "
    "'sois plus posé'). INTERDIT : déduire/affirmer une info perso, citer le contenu précis, "
    "stocker quoi que ce soit sur la personne. Réponds UNIQUEMENT par la consigne, sans guillemets."
)

def _daily_material(user_dict: dict) -> str:
    topics = ", ".join(user_dict.get("topics", []) or [])
    return (f"Interlocuteur : {user_dict.get('name','cette personne')}. "
            f"Interactions aujourd'hui : {user_dict.get('interactions',0)}. "
            f"Sujets : {topics or 'aucun en particulier'}.")


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
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=4, ensure_ascii=False)
        except OSError as e:
            logger.warning(f"⚠️ Sauvegarde {self.filename} impossible ({e}) — état non persisté.")

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
            # ⚠️ L'identifiant, pas seulement le pseudo : deux personnes peuvent porter
            # le meme nom d'affichage, et le pseudo change. Sans lui, le contexte d'un
            # membre pouvait remonter dans la reponse faite a un AUTRE.
            "user_id": uid,
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

        # ── Les échanges précédents ───────────────────────────────────────────────
        # ⚠️ Constaté en live le 2026-09-17, 16:32. L'utilisateur écrit « j'été avec
        # tony on fait la paix ? » et Malena répond « BÉBÉ KADOM ?? Tu recommences avec
        # sa ? » — une insulte vieille de DEUX HEURES, encore présente dans ce bloc.
        # Trois défauts se cumulaient, et chacun compte :
        #   1. le bloc arrivait APRÈS le message courant dans le prompt : le modèle
        #      lisait l'insulte en dernier et la prenait pour l'actuelle ;
        #   2. rien ne disait que c'était du passé (l'heure était stockée, jamais rendue) ;
        #   3. seules les lignes de l'utilisateur y figuraient — sans les réponses de
        #      Malena, ça ressemblait à une rafale de messages entrants NON traités,
        #      donc à des insultes auxquelles elle n'avait pas encore répondu.
        # Et un quatrième, latent : `conversations` est global, donc le contexte d'un
        # autre membre pouvait entrer dans la réponse faite à celui-ci.
        nom_connu = users.get(uid, {}).get("name")
        siens = [
            c for c in self.memory["conversations"]
            if str(c.get("user_id", "")) == uid
            or (not c.get("user_id") and nom_connu and c.get("user") == nom_connu)
        ]
        recent_chats = siens[-3:]
        if recent_chats:
            summary += ("\n[ÉCHANGES DÉJÀ PASSÉS — contexte seulement. Ils ont DÉJÀ reçu "
                        "leur réponse : n'y réponds pas une deuxième fois, et ne relance "
                        "pas un sujet clos si la personne est passée à autre chose.]")
            for c in recent_chats:
                heure = c.get("time", "?")
                summary += f"\n  ({heure}) {c.get('user', '?')} : {c.get('content', '')}"
                if c.get("response"):
                    summary += f"\n  ({heure}) Toi : {c['response']}"

        return summary

    def get_user_count(self):
        """Retourne le nombre d'utilisateurs uniques aujourd'hui."""
        return len(self.memory["users"])

    def get_daily_read(self, user_id) -> str:
        from datetime import datetime
        ud = self.memory.get("users", {}).get(str(user_id))
        if ud and ud.get("daily_read_date") == str(datetime.now().date()):
            return ud.get("daily_read", "") or ""
        return ""

    async def refresh_daily_read(self, user_id, llm_call):
        """Tâche de fond : 1 appel/jour si user actif. llm_call(sys_prompt, user_msg)->str|None."""
        from datetime import datetime
        try:
            ud = self.memory.get("users", {}).get(str(user_id))
            if not ud:
                return
            today = str(datetime.now().date())
            if ud.get("daily_read_date") == today:
                return
            if ud.get("interactions", 0) < MIN_DAILY_INTERACTIONS:
                return
            consigne = await llm_call(DAILY_READ_PROMPT, _daily_material(ud))
            if consigne:
                ud["daily_read"] = consigne.strip().strip('"').split("\n")[0][:160]
                ud["daily_read_date"] = today
                self.save_memory()
        except Exception as e:
            logger.debug(f"[LECTURE DU JOUR] mise a jour impossible : {e}")
