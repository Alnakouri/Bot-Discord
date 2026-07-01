import logging
from datetime import datetime

logger = logging.getLogger("shared_game_rewards")

try:
    from shared.shared_database import (
        add_reputation,
        get_game_cooldown,
        set_game_cooldown,
        get_game_daily_points,
        add_game_daily_points,
        get_game_pvp_cooldown,
        set_game_pvp_cooldown,
        DATABASE_AVAILABLE
    )
except ImportError:
    DATABASE_AVAILABLE = False
    
    # Mock data structure for standalone fallback
    _cooldowns = {}
    _daily_caps = {}
    _pvp_cooldowns = {}

    def add_reputation(user_id: int, points: int, reason: str = None) -> int:
        return points
    def get_game_cooldown(user_id: int, game_key: str, bot_name: str) -> float | None:
        return _cooldowns.get((user_id, game_key, bot_name))
    def set_game_cooldown(user_id: int, game_key: str, bot_name: str, ts: float):
        _cooldowns[(user_id, game_key, bot_name)] = ts
    def get_game_daily_points(user_id: int, date_str: str) -> int:
        return _daily_caps.get((user_id, date_str), 0)
    def add_game_daily_points(user_id: int, date_str: str, points: int):
        key = (user_id, date_str)
        _daily_caps[key] = _daily_caps.get(key, 0) + points
    def get_game_pvp_cooldown(pair_key: str) -> float | None:
        return _pvp_cooldowns.get(pair_key)
    def set_game_pvp_cooldown(pair_key: str, ts: float):
        _pvp_cooldowns[pair_key] = ts

REWARD_VALUES = {
    "tictactoe": {"win": 10, "draw": 3, "lose": 0},
    "connect4": {"win": 10, "draw": 3, "lose": 0},
    "rps": {"win": 5, "draw": 0, "lose": 0},
    "blackjack": {"win": 8, "blackjack": 15, "draw": 2, "lose": 0},
    "quiz": {"per_correct": 2}
}

def try_award(user_id: int, game_key: str, base_points: int, bot_name: str, opponent_id: int = None, date_override: str = None) -> int:
    """
    Checks the daily cap across all bots, game cooldown (per bot), and PvP anti-collusion.
    Returns the amount of reputation actually awarded.
    """
    if base_points <= 0:
        return 0

    now = datetime.now().timestamp()
    today = date_override if date_override else datetime.now().date().isoformat()
    
    # 1. PvP anti-collusion check
    if opponent_id is not None:
        if user_id == opponent_id:
            return 0  # No self-play rewards
            
        pair_key = f"{min(user_id, opponent_id)}-{max(user_id, opponent_id)}"
        last_pair_time = get_game_pvp_cooldown(pair_key)
        if last_pair_time is not None and (now - last_pair_time) < 600:
            logger.info(f"PvP pair {pair_key} in cooldown")
            return 0

    # 2. Cooldown per (user, game, bot)
    last_game_time = get_game_cooldown(user_id, game_key, bot_name)
    if last_game_time is not None and (now - last_game_time) < 600:
        logger.info(f"User {user_id} in cooldown for game {game_key} on bot {bot_name}")
        return 0

    # 3. Daily Cap check (max 50 rep/day/player from all minigames combined)
    today_points = get_game_daily_points(user_id, today)
    if today_points >= 50:
        logger.info(f"User {user_id} reached global daily cap of 50 reputation")
        return 0
        
    allowed_points = min(base_points, 50 - today_points)
    if allowed_points <= 0:
        return 0

    # 4. Save updates
    add_game_daily_points(user_id, today, allowed_points)
    set_game_cooldown(user_id, game_key, bot_name, now)
    if opponent_id is not None:
        set_game_pvp_cooldown(pair_key, now)
        
    # 5. Award reputation
    try:
        add_reputation(user_id, allowed_points, f"Mini-jeu ({bot_name}): {game_key}")
    except Exception as e:
        logger.error(f"Failed to award reputation via DB for {user_id}: {e}")

    return allowed_points
