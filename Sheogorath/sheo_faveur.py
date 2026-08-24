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
Système de Faveur du Prince pour Sheogorath.
Les mortels qui amusent le Prince de la Folie gagnent sa Faveur.
"""
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger("sheogorath")

FAVEUR_FILE = os.path.join(DATA_DIR, "sheo_faveurs.json")

# RANGS DE FAVEUR
RANKS = [
    {"name": "Mortel Ennuyeux", "min": 0, "emoji": "💤"},
    {"name": "Vermisseau Distrayant", "min": 5, "emoji": "🪱"},
    {"name": "Bouffon Acceptable", "min": 15, "emoji": "🤡"},
    {"name": "Amuseur du Prince", "min": 30, "emoji": "🎭"},
    {"name": "Favori du Prince", "min": 50, "emoji": "⭐"},
    {"name": "Champion du Chaos", "min": 75, "emoji": "👑"},
    {"name": "Demi-Prince de la Folie", "min": 100, "emoji": "🌀"},
]

# MOTS QUI RAPPORTENT DE LA FAVEUR
FAVEUR_WORDS = {
    # Mots clés -> points gagnés
    "fromage": 2, "cheese": 2, "roquefort": 3, "camembert": 3,
    "folie": 2, "chaos": 2, "wabbajack": 3,
    "papillon": 2, "thé": 1, "cuillère": 2,
    "sheogorath": 2, "sheo": 1, "prince": 1,
    "démence": 2, "mania": 2,
    "haskill": 2, "jyggalag": 3,
    "intestin": 2, "cervelle": 2, "dents": 1,
    "délire": 1, "absurde": 2, "bizarre": 1,
}

# MESSAGES DE GAIN DE FAVEUR
FAVEUR_GAIN_MESSAGES = [
    "✨ Le Prince t'accorde {pts} point(s) de Faveur ! (Total: {total})",
    "⭐ +{pts} Faveur ! Le Prince te regarde avec... est-ce de l'affection ? Non. Mais presque. ({total})",
    "🧀 Mmh ! Le mot magique ! +{pts} Faveur ! ({total})",
    "🎭 Tu amuses le Prince ! +{pts} ! ({total})",
    "👑 Intéressant, mortel... +{pts} Faveur ! ({total})",
]

RANK_UP_MESSAGES = [
    "🎉 **PROMOTION !** {user} passe au rang de **{rank}** {emoji} ! Le Prince est... impressionné ? Sûrement pas. Mais bon.",
    "🌀 **NOUVEAU RANG !** {user} → **{rank}** {emoji} ! Continue comme ça et je t'offrirai un fromage. Peut-être.",
    "⚡ **ASCENSION !** {user} est maintenant **{rank}** {emoji} ! Les étoiles tremblent ! (Non pas vraiment)",
]


class FaveurSystem:
    def __init__(self, filename=FAVEUR_FILE):
        self.filename = filename
        self.data = self.load()

    def load(self):
        if not os.path.exists(self.filename):
            return {}
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Erreur chargement faveurs: {e}")
            return {}

    def save(self):
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except OSError as e:
            logger.warning(f"⚠️ Sauvegarde {self.filename} impossible ({e}) — état non persisté.")

    def get_faveur(self, user_id):
        """Retourne les points de faveur d'un utilisateur."""
        uid = str(user_id)
        if uid not in self.data:
            return 0
        return self.data[uid].get("points", 0)

    def get_rank(self, user_id):
        """Retourne le rang actuel d'un utilisateur."""
        points = self.get_faveur(user_id)
        current_rank = RANKS[0]
        for rank in RANKS:
            if points >= rank["min"]:
                current_rank = rank
        return current_rank

    def add_faveur(self, user_id, user_name, points):
        """Ajoute des points de faveur. Retourne (nouveau_total, ancien_rang, nouveau_rang)."""
        uid = str(user_id)
        if uid not in self.data:
            self.data[uid] = {"name": user_name, "points": 0, "last_gain": None}

        old_rank = self.get_rank(user_id)
        self.data[uid]["points"] += points
        self.data[uid]["name"] = user_name
        self.data[uid]["last_gain"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_rank = self.get_rank(user_id)

        self.save()
        total = self.data[uid]["points"]
        rank_up = old_rank["name"] != new_rank["name"]

        return total, old_rank, new_rank, rank_up

    def get_leaderboard(self, limit=10):
        """Retourne le classement des top joueurs."""
        sorted_users = sorted(
            self.data.items(),
            key=lambda x: x[1].get("points", 0),
            reverse=True
        )[:limit]

        leaderboard = []
        for uid, udata in sorted_users:
            pts = udata.get("points", 0)
            rank = RANKS[0]
            for r in RANKS:
                if pts >= r["min"]:
                    rank = r
            leaderboard.append({
                "user_id": uid,
                "name": udata.get("name", "???"),
                "points": pts,
                "rank": rank,
            })
        return leaderboard

    def leaderboard(self, n=10):
        """Alias pour get_leaderboard dans PointsEconomy pour compatibilité."""
        return self.get_leaderboard(limit=n)

    def check_message_for_faveur(self, text):
        """Vérifie si un message contient des mots qui rapportent de la Faveur.
        Retourne le total de points gagnés (0 si rien)."""
        text_lower = text.lower()
        total_points = 0
        for word, pts in FAVEUR_WORDS.items():
            if word in text_lower:
                total_points += pts
        # Cap à 5 points max par message
        return min(total_points, 5)

    def get_rank_context(self, user_id):
        """Retourne une instruction de contexte pour le prompt LLM basée sur le rang."""
        rank = self.get_rank(user_id)
        points = self.get_faveur(user_id)
        if points == 0:
            return ""
        return (
            f"\n[FAVEUR DU PRINCE] Cet utilisateur a {points} points de Faveur. "
            f"Son rang : {rank['emoji']} {rank['name']}. "
            f"{'Traite-le avec un minimum de respect (pour toi).' if points >= 30 else 'Mortel ordinaire.'}"
        )
