import os
import json
import logging
import time
from datetime import datetime

logger = logging.getLogger("twitch_economy")

class PointsEconomy:
    def __init__(self, filename: str, ranks: list[dict], gain_min: int = 1, gain_max: int = 5, keywords: dict[str, int] = None, gain_cooldown: float = 60.0):
        self.filename = filename
        self.ranks = ranks
        self.gain_min = gain_min
        self.gain_max = gain_max
        self.keywords = keywords or {}
        self.gain_cooldown = gain_cooldown  # anti-farm : délai mini (s) entre 2 gains/login
        self.data = self.load()
        self.cooldowns = {} # login_lower -> timestamp

    def load(self) -> dict:
        if not os.path.exists(self.filename):
            return {}
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Erreur chargement économie ({self.filename}): {e}")
            return {}

    def save(self):
        tmp_path = self.filename + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.filename), exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            os.replace(tmp_path, self.filename)
        except Exception as e:
            logger.error(f"❌ Échec sauvegarde économie ({self.filename}): {e}")

    def get_points(self, login: str) -> int:
        user_key = login.lower()
        if user_key not in self.data:
            return 0
        return self.data[user_key].get("points", 0)

    def get_rank(self, login: str) -> dict:
        points = self.get_points(login)
        current_rank = self.ranks[0] if self.ranks else {"name": "Inconnu", "emoji": "❓", "threshold": 0}
        for rank in self.ranks:
            threshold = rank.get("threshold", rank.get("min", 0))
            if points >= threshold:
                current_rank = rank
        return current_rank

    def add_points(self, login: str, points: int) -> tuple[int, dict | None, dict | None, bool]:
        user_key = login.lower()
        if user_key not in self.data:
            self.data[user_key] = {"name": login, "points": 0, "last_gain": None}

        old_rank = self.get_rank(login)
        self.data[user_key]["points"] += points
        self.data[user_key]["name"] = login
        self.data[user_key]["last_gain"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_rank = self.get_rank(login)

        self.save()
        total = self.data[user_key]["points"]
        rank_up = old_rank.get("name") != new_rank.get("name")

        return total, old_rank, new_rank, rank_up

    def check_message(self, text: str) -> int:
        if not text:
            return 0
        text_lower = text.lower()
        pts = 0
        for word, val in self.keywords.items():
            if word in text_lower:
                pts += val
        if pts > 0:
            return min(pts, self.gain_max)
        
        # Fallback sur la longueur si aucun mot clé
        if len(text.strip()) > 15:
            return self.gain_min
        return 0

    def try_award(self, login: str, text: str) -> tuple[int, int, dict, dict, bool] | None:
        """check_message + anti-farm (cooldown par login) + add_points.
        Retourne (gained, total, old_rank, new_rank, rank_up) si des points sont
        accordés, sinon None (rien gagné OU cooldown actif). Empêche le farm par spam."""
        user_key = login.lower()
        now = time.time()
        if now - self.cooldowns.get(user_key, 0) < self.gain_cooldown:
            return None
        pts = self.check_message(text)
        if pts <= 0:
            return None
        self.cooldowns[user_key] = now
        total, old_rank, new_rank, rank_up = self.add_points(login, pts)
        return pts, total, old_rank, new_rank, rank_up

    def leaderboard(self, n=10) -> list[tuple[str, int]]:
        sorted_users = sorted(
            self.data.items(),
            key=lambda x: x[1].get("points", 0),
            reverse=True
        )[:n]
        return [(item[1].get("name", item[0]), item[1].get("points", 0)) for item in sorted_users]
