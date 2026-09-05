import os
import json
import re
import logging
from datetime import datetime

logger = logging.getLogger("sugar_memory")

STOPWORDS_MEMORY = {
    "le", "la", "les", "un", "une", "des", "ce", "cet", "cette", "ces",
    "mon", "ton", "son", "ma", "ta", "sa", "mes", "tes", "ses", "nos", "vos", "leurs",
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles", "lui", "leur", "eux",
    "me", "te", "se", "y", "en", "moi", "toi", "soi", "avec", "sans", "pour", "dans",
    "qui", "que", "quoi", "dont", "où", "quel", "quels", "quelle", "quelles",
    "du", "au", "aux", "de", "à", "et", "ou", "mais", "donc", "car", "ni", "si", "or",
    "est", "sont", "était", "étaient", "suis", "es", "sommes", "êtes", "avez", "ont", "a", "as",
    "plus", "moins", "très", "tout", "tous", "toute", "toutes", "bien", "comme", "alors",
    "faire", "fait", "font", "peux", "peut"
}

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

def tokenize(text: str) -> set[str]:
    """Nettoie, filtre les stopwords et extrait les mots de 3 lettres ou plus."""
    if not text:
        return set()
    cleaned = text.lower()
    cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
    words = cleaned.split()
    return {w for w in words if len(w) >= 3 and w not in STOPWORDS_MEMORY}

class FactMemory:
    """
    Mémoire de faits horodatés et cloisonnés par utilisateur.
    Format d'un fait : {"fact": str, "ts": ISO_date, "last_used": ISO_date}
    """
    def __init__(self, filename):
        self.filename = filename
        self.facts = {}
        self.load_facts()

    def load_facts(self):
        if not os.path.exists(self.filename):
            self.facts = {}
            return
            
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                
            # Migration à la volée et validation du format
            migrated_data = {}
            for user_id, fact_list in raw_data.items():
                if not isinstance(fact_list, list):
                    continue
                uid = str(user_id)
                migrated_data[uid] = []
                for item in fact_list:
                    if isinstance(item, str):
                        # Vieux format : simple chaîne
                        migrated_data[uid].append({
                            "fact": item,
                            "ts": datetime.now().isoformat(),
                            "last_used": datetime.now().isoformat()
                        })
                    elif isinstance(item, dict) and "fact" in item:
                        # Nouveau format
                        migrated_data[uid].append({
                            "fact": item["fact"],
                            "ts": item.get("ts", datetime.now().isoformat()),
                            "last_used": item.get("last_used", datetime.now().isoformat())
                        })
                # Cap à 30 faits
                if len(migrated_data[uid]) > 30:
                    # Trier par last_used croissant pour éliminer les moins récents
                    migrated_data[uid].sort(key=lambda x: x.get("last_used", ""))
                    migrated_data[uid] = migrated_data[uid][-30:]
            self.facts = migrated_data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Erreur chargement faits mémoire long terme : {e}")
            self.facts = {}

    def save_facts(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.filename)), exist_ok=True)
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.facts, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur sauvegarde faits mémoire long terme : {e}")

    def get_raw_facts(self, user_id) -> list[dict]:
        """Retourne la liste des dicts de faits bruts pour un user."""
        return self.facts.get(str(user_id), [])

    def get_relevant_facts(self, user_id, message: str, k=3) -> list[str]:
        """
        Calcule le recouvrement lexical entre le message et chaque fait de l'utilisateur.
        Met à jour last_used pour les faits renvoyés, sauvegarde et retourne
        les k faits les plus pertinents au format: "(appris le AAAA-MM-JJ) <fait>"
        """
        uid = str(user_id)
        user_facts = self.facts.get(uid, [])
        if not user_facts:
            return []
            
        message_tokens = tokenize(message)
        if not message_tokens:
            # Si aucun mot significatif dans le message, renvoyer les plus récemment utilisés
            sorted_facts = sorted(user_facts, key=lambda x: x.get("last_used", ""), reverse=True)
            results = sorted_facts[:k]
            # Mettre à jour last_used
            now_iso = datetime.now().isoformat()
            for f in results:
                f["last_used"] = now_iso
            self.save_facts()
            
            formatted = []
            for f in results:
                date_str = f["ts"].split("T")[0]
                formatted.append(f"(appris le {date_str}) {f['fact']}")
            return formatted

        # Calcul des scores
        scored_facts = []
        for fact_obj in user_facts:
            fact_tokens = tokenize(fact_obj["fact"])
            score = len(message_tokens.intersection(fact_tokens))
            scored_facts.append((score, fact_obj))
            
        # Tri : par score décroissant, puis par last_used décroissant
        scored_facts.sort(key=lambda x: (x[0], x[1].get("last_used", "")), reverse=True)
        
        # Sélection des k premiers
        results = [item[1] for item in scored_facts[:k]]
        
        # Mettre à jour la date d'utilisation
        now_iso = datetime.now().isoformat()
        for f in results:
            f["last_used"] = now_iso
        self.save_facts()
        
        # Formater pour le prompt
        formatted = []
        for f in results:
            date_str = f["ts"].split("T")[0]
            formatted.append(f"(appris le {date_str}) {f['fact']}")
        return formatted

    def add_fact(self, user_id, fact_str: str):
        """Ajoute un fait pour un utilisateur, gère la limite des 30 faits (éviction par last_used)."""
        if not fact_str or not fact_str.strip():
            return
            
        uid = str(user_id)
        if uid not in self.facts:
            self.facts[uid] = []
            
        # Vérifier si le fait existe déjà
        cleaned_fact = fact_str.strip()
        existing = next((f for f in self.facts[uid] if f["fact"].lower() == cleaned_fact.lower()), None)
        
        now_iso = datetime.now().isoformat()
        if existing:
            existing["last_used"] = now_iso
        else:
            new_fact = {
                "fact": cleaned_fact,
                "ts": now_iso,
                "last_used": now_iso
            }
            self.facts[uid].append(new_fact)
            
            # Éviction si > 30 faits
            if len(self.facts[uid]) > 30:
                # Trier par last_used croissant (le plus ancien en premier)
                self.facts[uid].sort(key=lambda x: x.get("last_used", ""))
                self.facts[uid].pop(0) # Retirer le plus ancien
                
        self.save_facts()
        logger.info(f"🧠 [LTM] Fait appris/mis à jour pour {uid}: {cleaned_fact}")


class DailyMemory:
    """
    Mémoire quotidienne qui se réinitialise chaque jour.
    Archivage de la journée sous forme de ligne JSONL à chaque reset.
    """
    def __init__(self, filename, on_reset=None):
        self.filename = filename
        self.on_reset = on_reset
        self.memory = {}
        self.load_memory()
        self.check_reset()

    def load_memory(self):
        if not os.path.exists(self.filename):
            self.memory = {"date": str(datetime.now().date()), "users": {}, "conversations": []}
            return
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                self.memory = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Erreur chargement mémoire quotidienne : {e}")
            self.memory = {"date": str(datetime.now().date()), "users": {}, "conversations": []}

    def save_memory(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.filename)), exist_ok=True)
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur sauvegarde mémoire quotidienne : {e}")

    def check_reset(self):
        today = str(datetime.now().date())
        if self.memory.get("date") != today:
            logger.info(f"🌅 Reset de la mémoire quotidienne ({self.filename}) pour un nouveau jour.")
            
            # 1. Appel du callback on_reset si présent (pour consolidation)
            if self.on_reset:
                try:
                    import asyncio
                    import inspect
                    if inspect.iscoroutinefunction(self.on_reset):
                        # Callback asynchrone
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(self.on_reset(self.memory))
                        except RuntimeError:
                            # Hors boucle d'événements (par ex. à l'init synchrone)
                            # On l'exécute de manière bloquante si pas de boucle
                            asyncio.run(self.on_reset(self.memory))
                    else:
                        self.on_reset(self.memory)
                except Exception as e:
                    logger.error(f"Erreur dans le callback on_reset : {e}")
            
            # 2. Archivage dans _archive.jsonl
            base, ext = os.path.splitext(self.filename)
            archive_path = f"{base}_archive.jsonl"
            try:
                with open(archive_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(self.memory, ensure_ascii=False) + "\n")
                logger.info(f"📁 Mémoire quotidienne archivée dans : {archive_path}")
            except Exception as e:
                logger.error(f"Impossible d'archiver la mémoire quotidienne : {e}")
                
            # 3. Réinitialisation
            self.memory = {"date": today, "users": {}, "conversations": []}
            self.save_memory()

    def add_interaction(self, user_id, user_name, content, bot_response=None):
        self.check_reset()
        uid = str(user_id)
        if "users" not in self.memory:
            self.memory["users"] = {}
        if "conversations" not in self.memory:
            self.memory["conversations"] = []
            
        if uid not in self.memory["users"]:
            self.memory["users"][uid] = {"name": user_name, "interactions": 0, "topics": []}
            
        self.memory["users"][uid]["interactions"] += 1
        
        # Extraction de thèmes simples (les premiers mots significatifs)
        words = content.split()
        if len(words) > 3:
            topic_snippet = " ".join(words[:5]) + "..."
            self.memory["users"][uid]["topics"].append(topic_snippet)
            # Garder les 5 derniers sujets
            self.memory["users"][uid]["topics"] = self.memory["users"][uid]["topics"][-5:]
            
        entry = {
            "time": str(datetime.now().strftime("%H:%M")),
            "user_id": uid,
            "user": user_name,
            "content": content,
            "response": bot_response
        }
        self.memory["conversations"].append(entry)
        
        # Limite de 50 conversations pour le contexte court terme
        if len(self.memory["conversations"]) > 50:
            self.memory["conversations"].pop(0)
            
        self.save_memory()

    def get_context_summary(self, user_id) -> str:
        """Retourne un résumé des interactions du jour avec cet utilisateur et les derniers messages."""
        uid = str(user_id)
        summary = ""
        
        users = self.memory.get("users", {})
        if uid in users:
            u_data = users[uid]
            topics_str = ", ".join(u_data.get("topics", []))
            summary += f"\n[MÉMOIRE JOURNÉE] Interactions aujourd'hui : {u_data['interactions']}. Sujets abordés : {topics_str}."
            
        # Récupérer les 3 derniers échanges globaux
        recent_chats = self.memory.get("conversations", [])[-3:]
        if recent_chats:
            chats_str = " | ".join([f"{c['user']}: {c['content']}" for c in recent_chats])
            summary += f"\n[RÉCENT] {chats_str}"
            
        return summary

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
