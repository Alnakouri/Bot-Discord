import os
import sys
import tempfile
import pytest

# Add MaiqBot to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "MaiqBot"))

import game_engines
import game_rewards


@pytest.fixture(autouse=True)
def setup_temp_rewards_file():
    # Redirect rewards JSON to a temporary file for tests
    fd, path = tempfile.mkstemp()
    os.close(fd)
    old_file = game_rewards.REWARDS_FILE
    game_rewards.REWARDS_FILE = path
    yield
    game_rewards.REWARDS_FILE = old_file
    try:
        os.unlink(path)
    except Exception:
        pass


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
    # A perfect AI against random moves should never lose.
    import random
    
    for _ in range(50):
        game = game_engines.TicTacToe(current_turn="X")
        while game.winner() is None:
            if game.current_turn == "X":
                # Random move
                moves = game.available()
                game.play(random.choice(moves))
            else:
                # Pro AI move
                ai_move = game_engines.get_ttt_best_move(game.board, "O", difficulty="pro")
                game.play(ai_move)
        
        # O should never lose
        assert game.winner() != "X"


# ==========================================
# Connect4 Tests
# ==========================================

def test_connect4_winner():
    # Test horizontal win
    grid = [[None] * 7 for _ in range(6)]
    for col in range(4):
        grid[5][col] = "R"
    game = game_engines.Connect4(board=grid)
    assert game.winner() == "R"

    # Test vertical win
    grid = [[None] * 7 for _ in range(6)]
    for row in range(2, 6):
        grid[row][0] = "Y"
    game = game_engines.Connect4(board=grid)
    assert game.winner() == "Y"

    # Test diagonal down-right win
    grid = [[None] * 7 for _ in range(6)]
    for i in range(4):
        grid[i][i] = "R"
    game = game_engines.Connect4(board=grid)
    assert game.winner() == "R"


def test_connect4_ai_blocking():
    # R is player, Y is AI. R has 3 tokens vertically on column 2 (from bottom).
    # AI must block at column 2.
    grid = [[None] * 7 for _ in range(6)]
    grid[5][2] = "R"
    grid[4][2] = "R"
    grid[3][2] = "R"
    
    # AI should choose col 2
    best_col = game_engines.get_c4_best_col(grid, "Y", depth=3)
    assert best_col == 2


# ==========================================
# RPS Tests
# ==========================================

def test_rps_resolve():
    game = game_engines.RPSGame()
    
    # Resolves
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
    # Hand value logic
    assert game_engines.BlackjackGame.hand_value(["10", "A"]) == 21
    assert game_engines.BlackjackGame.hand_value(["A", "A"]) == 12  # One ace is 11, the other is 1
    assert game_engines.BlackjackGame.hand_value(["10", "9", "A"]) == 20
    assert game_engines.BlackjackGame.hand_value(["K", "Q", "J"]) == 30
    assert game_engines.BlackjackGame.hand_value(["A", "A", "A"]) == 13

    # Basic Game flow (with deterministic deck via seed)
    game = game_engines.BlackjackGame(seed=42)
    assert len(game.player_hand) == 2
    assert len(game.dealer_hand) == 2
    
    # Stand -> dealer hits until >= 17
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
    
    # Verify no duplicates
    q_texts = [q["q"] for q in quiz.questions]
    assert len(set(q_texts)) == 5
    
    # Play
    first_q = quiz.get_current_question()
    is_correct = quiz.answer_question(first_q["answer_idx"])
    assert is_correct is True
    assert quiz.score == 1


# ==========================================
# Rewards & Anti-farm Tests
# ==========================================

def test_rewards_cooldown_and_caps():
    # First award is successful
    awarded = game_rewards.try_award(12345, "tictactoe", 10)
    assert awarded == 10

    # Second award for same user & game is blocked due to 10 min cooldown
    awarded = game_rewards.try_award(12345, "tictactoe", 10)
    assert awarded == 0

    # Award for different game is allowed
    awarded = game_rewards.try_award(12345, "connect4", 10)
    assert awarded == 10

    # Let's test the daily cap. Total for 12345 so far is 20 points (10 ttt, 10 c4).
    # Remaining before cap is 30.
    awarded = game_rewards.try_award(12345, "rps", 20)
    assert awarded == 20 # Total 40
    
    awarded = game_rewards.try_award(12345, "blackjack", 20)
    assert awarded == 10 # Capped at 50 total for today

    # Verify no more awards
    awarded = game_rewards.try_award(12345, "quiz", 10)
    assert awarded == 0


def test_rewards_pvp_collusion():
    # Same players pair cooldown
    p1 = 111
    p2 = 222
    
    # First duel award
    awarded = game_rewards.try_award(p1, "tictactoe", 10, opponent_id=p2)
    assert awarded == 10
    
    # Second duel award between same pair within 10 min is blocked
    awarded = game_rewards.try_award(p2, "tictactoe", 10, opponent_id=p1)
    assert awarded == 0
    
    # Duel against yourself is blocked
    awarded = game_rewards.try_award(p1, "tictactoe", 10, opponent_id=p1)
    assert awarded == 0
