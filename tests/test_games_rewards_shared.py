import sys
import os
import pytest

# Add shared to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import shared.games.rewards as rewards
from shared.shared_database import init_database


@pytest.fixture(autouse=True)
def clean_db():
    # Make sure tables are initialized
    init_database()
    # Clean tables for test repeatability
    from shared.shared_database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game_cooldowns")
    cursor.execute("DELETE FROM game_daily_caps")
    cursor.execute("DELETE FROM game_pvp_cooldowns")
    conn.commit()
    conn.close()


def test_cooldown_per_bot():
    user_id = 99999
    
    # First award on Bot A
    awarded1 = rewards.try_award(user_id, "tictactoe", 10, "M'aiq")
    assert awarded1 == 10
    
    # Second award on Bot A within 10 min -> blocked
    awarded2 = rewards.try_award(user_id, "tictactoe", 10, "M'aiq")
    assert awarded2 == 0
    
    # Award on Bot B for same game is allowed (cooldown is per bot!)
    awarded3 = rewards.try_award(user_id, "tictactoe", 10, "Sheogorath")
    assert awarded3 == 10


def test_shared_daily_cap():
    user_id = 88888
    date_str = "2026-07-01"
    
    # Award 20 points from M'aiq
    awarded1 = rewards.try_award(user_id, "tictactoe", 20, "M'aiq", date_override=date_str)
    assert awarded1 == 20
    
    # Award 20 points from Sheogorath
    awarded2 = rewards.try_award(user_id, "connect4", 20, "Sheogorath", date_override=date_str)
    assert awarded2 == 20
    
    # Award 20 points from Johnny -> capped at 50 total (so 10 points awarded)
    awarded3 = rewards.try_award(user_id, "rps", 20, "Johnny", date_override=date_str)
    assert awarded3 == 10
    
    # Next awards are completely blocked
    awarded4 = rewards.try_award(user_id, "blackjack", 20, "Alfred", date_override=date_str)
    assert awarded4 == 0
