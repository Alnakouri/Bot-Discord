import os
import json
import logging
from datetime import datetime

logger = logging.getLogger("maiq_game_rewards")

# Fallback import of add_reputation
try:
    from shared.shared_database import add_reputation
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    def add_reputation(user_id: int, points: int, reason: str = None) -> int:
        logger.info(f"[FALLBACK DB] add_reputation({user_id}, {points}, {reason})")
        return points

REWARDS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "maiq_games_rewards.json")

# Points constants
REWARD_VALUES = {
    "tictactoe": {"win": 10, "draw": 3, "lose": 0},
    "connect4": {"win": 10, "draw": 3, "lose": 0},
    "rps": {"win": 5, "draw": 0, "lose": 0},
    "blackjack": {"win": 8, "blackjack": 15, "draw": 2, "lose": 0},
    "quiz": {"per_correct": 2}
}

def load_rewards_data() -> dict:
    if not os.path.exists(REWARDS_FILE):
        return {"cooldowns": {}, "daily_caps": {}, "pvp_pairs": {}}
    try:
        with open(REWARDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error loading rewards JSON: {e}")
        return {"cooldowns": {}, "daily_caps": {}, "pvp_pairs": {}}

def save_rewards_data(data: dict):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(REWARDS_FILE)), exist_ok=True)
        with open(REWARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving rewards JSON: {e}")

def try_award(user_id: int, game_key: str, base_points: int, opponent_id: int = None) -> int:
    """
    Checks the daily cap, game cooldown, and PvP anti-collusion.
    Returns the amount of reputation actually awarded.
    """
    if base_points <= 0:
        return 0

    now = datetime.now().timestamp()
    today = datetime.now().date().isoformat()
    user_str = str(user_id)
    
    data = load_rewards_data()
    
    # 1. PvP anti-collusion check
    if opponent_id is not None:
        opponent_str = str(opponent_id)
        if user_str == opponent_str:
            return 0  # No self-play rewards
            
        pair_key = f"{min(user_id, opponent_id)}-{max(user_id, opponent_id)}"
        last_pair_time = data.setdefault("pvp_pairs", {}).get(pair_key)
        if last_pair_time is not None and (now - last_pair_time) < 600:
            logger.info(f"PvP pair {pair_key} in cooldown")
            return 0

    # 2. Cooldown per (user, game)
    user_cooldowns = data.setdefault("cooldowns", {}).setdefault(user_str, {})
    last_game_time = user_cooldowns.get(game_key)
    if last_game_time is not None and (now - last_game_time) < 600:
        logger.info(f"User {user_id} in cooldown for game {game_key}")
        return 0

    # 3. Daily Cap check (max 50 rep/day/player from minigames)
    user_caps = data.setdefault("daily_caps", {}).setdefault(user_str, {})
    today_points = user_caps.get(today, 0)
    if today_points >= 50:
        logger.info(f"User {user_id} reached daily cap of 50 reputation")
        return 0
        
    allowed_points = min(base_points, 50 - today_points)
    if allowed_points <= 0:
        return 0

    # 4. Success -> update structures and save
    user_caps[today] = today_points + allowed_points
    user_cooldowns[game_key] = now
    if opponent_id is not None:
        data["pvp_pairs"][pair_key] = now
        
    save_rewards_data(data)

    # 5. Award reputation
    try:
        add_reputation(user_id, allowed_points, f"Mini-jeu: {game_key}")
    except Exception as e:
        logger.error(f"Failed to award reputation via DB for {user_id}: {e}")

    return allowed_points
