import sys
import os
import pytest

# Add shared to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.games.views import setup_games, BlackjackView, QuizView, TicTacToeView
import logging

class MockBot:
    def __init__(self):
        self.commands_dict = {}
        self.user = type('obj', (object,), {'id': 999, 'name': 'TestBot', 'bot': True})()
        
    def command(self, *args, **kwargs):
        def decorator(func):
            name = kwargs.get('name', func.__name__)
            self.commands_dict[name] = func
            return func
        return decorator


def test_setup_games_registration():
    bot = MockBot()
    logger = logging.getLogger("test")
    
    dummy_persona = {
        "name": "TestPersona",
        "is_default_host": True,
        "taunts": ["taunt1"],
        "win_lines": ["win1"],
        "lose_lines": ["lose1"],
        "draw_lines": ["draw1"],
        "timeout_lines": ["time1"],
        "quiz_questions": [{"q": "Q", "choices": ["A"], "answer_idx": 0, "flavor": ""}]
    }
    
    setup_games(bot, logger, dummy_persona)
    
    # Assert commands were registered
    assert "jeux" in bot.commands_dict
    assert "morpion" in bot.commands_dict
    assert "puissance4" in bot.commands_dict
    assert "pfc" in bot.commands_dict
    assert "blackjack" in bot.commands_dict
    assert "quiz" in bot.commands_dict
    assert "defi" in bot.commands_dict


def test_persona_injected_in_views():
    dummy_persona = {
        "name": "TestPersona",
        "is_default_host": False,
        "taunts": ["taunt1"],
        "win_lines": ["win1"],
        "lose_lines": ["lose1"],
        "draw_lines": ["draw1"],
        "timeout_lines": ["time1"],
        "quiz_questions": [{"q": "Q", "choices": ["A"], "answer_idx": 0, "flavor": ""}]
    }
    
    player = type('obj', (object,), {'id': 123, 'display_name': 'PlayerX'})()
    
    # Check TicTacToeView
    view_ttt = TicTacToeView(player, "TestPersona", dummy_persona)
    assert view_ttt.persona["name"] == "TestPersona"
    assert view_ttt.persona["win_lines"] == ["win1"]
    
    # Check BlackjackView
    view_bj = BlackjackView(player, dummy_persona)
    assert view_bj.persona["name"] == "TestPersona"
    assert view_bj.persona["lose_lines"] == ["lose1"]
    
    # Check QuizView
    view_qz = QuizView(player, dummy_persona)
    assert view_qz.persona["name"] == "TestPersona"
    assert view_qz.persona["quiz_questions"][0]["q"] == "Q"
