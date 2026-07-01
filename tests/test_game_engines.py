import os
import sys
import pytest

# Add shared to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import shared.games.engines as game_engines
import shared.games.rewards as game_rewards
from shared.shared_database import init_database


@pytest.fixture(autouse=True)
def clean_db():
    init_database()
    from shared.shared_database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game_cooldowns")
    cursor.execute("DELETE FROM game_daily_caps")
    cursor.execute("DELETE FROM game_pvp_cooldowns")
    conn.commit()
    conn.close()


# ==========================================
# TicTacToe Tests
# ==========================================

def test_tictactoe_winner():
    # Test rows
    game = game_engines.TicTacToe(board=["X", "X", "X", None, None, None, None, None, None])
    assert game.winner() == "X"

    # Test columns
    game = game_engines.TicTacToe(board=["O", None, None, "O", None, None, "O", None, None])
    assert game.winner() == "O"

    # Test diagonals
    game = game_engines.TicTacToe(board=["X", None, None, None, "X", None, None, None, "X"])
    assert game.winner() == "X"

    # Test draw
    game = game_engines.TicTacToe(board=["X", "O", "X", "X", "O", "O", "O", "X", "X"])
    assert game.winner() == "draw"

    # Test incomplete
    game = game_engines.TicTacToe(board=["X", None, "O", None, None, None, None, None, None])
    assert game.winner() is None


def test_tictactoe_ai_perfect():
    import random
    
    for _ in range(50):
        game = game_engines.TicTacToe(current_turn="X")
        while game.winner() is None:
            if game.current_turn == "X":
                moves = game.available()
                game.play(random.choice(moves))
            else:
                ai_move = game_engines.get_ttt_best_move(game.board, "O", difficulty="pro")
                game.play(ai_move)
        
        assert game.winner() != "X"


# ==========================================
# Connect4 Tests
# ==========================================

def test_connect4_winner():
    grid = [[None] * 7 for _ in range(6)]
    for col in range(4):
        grid[5][col] = "R"
    game = game_engines.Connect4(board=grid)
    assert game.winner() == "R"

    grid = [[None] * 7 for _ in range(6)]
    for row in range(2, 6):
        grid[row][0] = "Y"
    game = game_engines.Connect4(board=grid)
    assert game.winner() == "Y"

    grid = [[None] * 7 for _ in range(6)]
    for i in range(4):
        grid[i][i] = "R"
    game = game_engines.Connect4(board=grid)
    assert game.winner() == "R"


def test_connect4_ai_blocking():
    grid = [[None] * 7 for _ in range(6)]
    grid[5][2] = "R"
    grid[4][2] = "R"
    grid[3][2] = "R"
    
    best_col = game_engines.get_c4_best_col(grid, "Y", depth=3)
    assert best_col == 2


# ==========================================
# RPS Tests
# ==========================================

def test_rps_resolve():
    game = game_engines.RPSGame()
    
    assert game.resolve_round("pierre", "ciseaux") == "a"
    assert game.resolve_round("feuille", "pierre") == "a"
    assert game.resolve_round("ciseaux", "feuille") == "a"
    assert game.resolve_round("pierre", "feuille") == "b"
    assert game.resolve_round("pierre", "pierre") == "draw"
    
    assert game.score_a == 3
    assert game.score_b == 1
    assert game.winner() == "a"


# ==========================================
# Blackjack Tests
# ==========================================

def test_blackjack():
    assert game_engines.BlackjackGame.hand_value(["10", "A"]) == 21
    assert game_engines.BlackjackGame.hand_value(["A", "A"]) == 12
    assert game_engines.BlackjackGame.hand_value(["10", "9", "A"]) == 20
    assert game_engines.BlackjackGame.hand_value(["K", "Q", "J"]) == 30
    assert game_engines.BlackjackGame.hand_value(["A", "A", "A"]) == 13

    game = game_engines.BlackjackGame(seed=42)
    assert len(game.player_hand) == 2
    assert len(game.dealer_hand) == 2
    
    game.player_stand()
    assert game.hand_value(game.dealer_hand) >= 17


# ==========================================
# Quiz Tests
# ==========================================

def test_quiz():
    q_bank = [
        {"q": "Q1", "choices": ["A", "B"], "answer_idx": 0, "flavor": ""},
        {"q": "Q2", "choices": ["A", "B"], "answer_idx": 1, "flavor": ""},
        {"q": "Q3", "choices": ["A", "B"], "answer_idx": 0, "flavor": ""},
        {"q": "Q4", "choices": ["A", "B"], "answer_idx": 1, "flavor": ""},
        {"q": "Q5", "choices": ["A", "B"], "answer_idx": 0, "flavor": ""},
        {"q": "Q6", "choices": ["A", "B"], "answer_idx": 1, "flavor": ""}
    ]
    
    quiz = game_engines.QuizGame(q_bank, num_questions=5, seed=42)
    assert len(quiz.questions) == 5
    
    q_texts = [q["q"] for q in quiz.questions]
    assert len(set(q_texts)) == 5
    
    first_q = quiz.get_current_question()
    is_correct = quiz.answer_question(first_q["answer_idx"])
    assert is_correct is True
    assert quiz.score == 1


# ==========================================
# Rewards & Anti-farm Tests
# ==========================================

def test_rewards_cooldown_and_caps():
    awarded = game_rewards.try_award(12345, "tictactoe", 10, "M'aiq")
    assert awarded == 10

    awarded = game_rewards.try_award(12345, "tictactoe", 10, "M'aiq")
    assert awarded == 0

    awarded = game_rewards.try_award(12345, "connect4", 10, "M'aiq")
    assert awarded == 10

    awarded = game_rewards.try_award(12345, "rps", 20, "M'aiq")
    assert awarded == 20
    
    awarded = game_rewards.try_award(12345, "blackjack", 20, "M'aiq")
    assert awarded == 10

    awarded = game_rewards.try_award(12345, "quiz", 10, "M'aiq")
    assert awarded == 0


def test_rewards_pvp_collusion():
    p1 = 111
    p2 = 222
    
    awarded = game_rewards.try_award(p1, "tictactoe", 10, "M'aiq", opponent_id=p2)
    assert awarded == 10
    
    awarded = game_rewards.try_award(p2, "tictactoe", 10, "M'aiq", opponent_id=p1)
    assert awarded == 0
    
    awarded = game_rewards.try_award(p1, "tictactoe", 10, "M'aiq", opponent_id=p1)
    assert awarded == 0
