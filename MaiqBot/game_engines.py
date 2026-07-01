import random

# ==========================================
# TicTacToe (Morpion)
# ==========================================

class TicTacToe:
    def __init__(self, board=None, current_turn="X"):
        self.board = board if board is not None else [None] * 9
        self.current_turn = current_turn

    def play(self, idx: int) -> bool:
        if idx < 0 or idx >= 9 or self.board[idx] is not None:
            return False
        self.board[idx] = self.current_turn
        self.current_turn = "O" if self.current_turn == "X" else "X"
        return True

    def available(self) -> list[int]:
        return [i for i, v in enumerate(self.board) if v is None]

    def winner(self) -> str | None:
        win_patterns = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6)
        ]
        for a, b, c in win_patterns:
            if self.board[a] is not None and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        if None not in self.board:
            return "draw"
        return None

    def serialize(self) -> str:
        lines = []
        for i in range(0, 9, 3):
            row = [self.board[j] or " " for j in range(i, i+3)]
            lines.append(" | ".join(row))
        return "\n---------\n".join(lines)


def ttt_minimax(board, depth, is_maximizing, ai_mark, player_mark):
    win_patterns = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6)
    ]
    
    def check_win(b):
        for a, b_idx, c in win_patterns:
            if b[a] is not None and b[a] == b[b_idx] == b[c]:
                return b[a]
        if None not in b:
            return "draw"
        return None
        
    res = check_win(board)
    if res == ai_mark:
        return 10 - depth
    elif res == player_mark:
        return depth - 10
    elif res == "draw":
        return 0
        
    if is_maximizing:
        best_score = -float('inf')
        for i in range(9):
            if board[i] is None:
                board[i] = ai_mark
                score = ttt_minimax(board, depth + 1, False, ai_mark, player_mark)
                board[i] = None
                best_score = max(best_score, score)
        return best_score
    else:
        best_score = float('inf')
        for i in range(9):
            if board[i] is None:
                board[i] = player_mark
                score = ttt_minimax(board, depth + 1, True, ai_mark, player_mark)
                board[i] = None
                best_score = min(best_score, score)
        return best_score


def get_ttt_best_move(board, ai_mark, difficulty="normal"):
    available = [i for i, v in enumerate(board) if v is None]
    if not available:
        return None
        
    player_mark = "O" if ai_mark == "X" else "X"
    
    if difficulty == "normal" and random.random() < 0.15:
        return random.choice(available)
        
    best_score = -float('inf')
    best_moves = []
    
    for i in available:
        board[i] = ai_mark
        score = ttt_minimax(board, 0, False, ai_mark, player_mark)
        board[i] = None
        if score > best_score:
            best_score = score
            best_moves = [i]
        elif score == best_score:
            best_moves.append(i)
            
    return random.choice(best_moves)


# ==========================================
# Connect4 (Puissance 4)
# ==========================================

class Connect4:
    def __init__(self, board=None, current_turn="R"):
        self.rows = 6
        self.cols = 7
        self.board = board if board is not None else [[None] * 7 for _ in range(6)]
        self.current_turn = current_turn

    def valid_cols(self) -> list[int]:
        return [c for c in range(7) if self.board[0][c] is None]

    def drop(self, col: int) -> bool:
        if col < 0 or col >= 7 or self.board[0][col] is not None:
            return False
        for r in range(5, -1, -1):
            if self.board[r][col] is None:
                self.board[r][col] = self.current_turn
                self.current_turn = "Y" if self.current_turn == "R" else "R"
                return True
        return False

    def is_full(self) -> bool:
        return all(self.board[0][c] is not None for c in range(7))

    def winner(self) -> str | None:
        return c4_check_win(self.board)

    def serialize(self) -> str:
        res = []
        for r in range(6):
            row_chars = []
            for c in range(7):
                val = self.board[r][c]
                if val == "R":
                    row_chars.append("🔴")
                elif val == "Y":
                    row_chars.append("🟡")
                else:
                    row_chars.append("⚪")
            res.append("".join(row_chars))
        return "\n".join(res)


def c4_check_win(b):
    # Horizontal
    for r in range(6):
        for c in range(4):
            if b[r][c] is not None and b[r][c] == b[r][c+1] == b[r][c+2] == b[r][c+3]:
                return b[r][c]
    # Vertical
    for c in range(7):
        for r in range(3):
            if b[r][c] is not None and b[r][c] == b[r+1][c] == b[r+2][c] == b[r+3][c]:
                return b[r][c]
    # Diagonal down-right
    for r in range(3):
        for c in range(4):
            if b[r][c] is not None and b[r][c] == b[r+1][c+1] == b[r+2][c+2] == b[r+3][c+3]:
                return b[r][c]
    # Diagonal up-right
    for r in range(3, 6):
        for c in range(4):
            if b[r][c] is not None and b[r][c] == b[r-1][c+1] == b[r-2][c+2] == b[r-3][c+3]:
                return b[r][c]
    # Check draw
    if all(b[0][c] is not None for c in range(7)):
        return "draw"
    return None


def evaluate_window(window, ai_mark, player_mark):
    score = 0
    ai_count = window.count(ai_mark)
    player_count = window.count(player_mark)
    empty_count = window.count(None)
    
    if ai_count == 4:
        score += 1000
    elif ai_count == 3 and empty_count == 1:
        score += 15
    elif ai_count == 2 and empty_count == 2:
        score += 3
        
    if player_count == 3 and empty_count == 1:
        score -= 80
    elif player_count == 2 and empty_count == 2:
        score -= 4
        
    return score


def evaluate_board(board, ai_mark):
    player_mark = "Y" if ai_mark == "R" else "R"
    score = 0
    
    # Center preference
    center_array = [board[r][3] for r in range(6)]
    center_count = center_array.count(ai_mark)
    score += center_count * 4
    
    # Horizontal
    for r in range(6):
        for c in range(4):
            window = [board[r][c+i] for i in range(4)]
            score += evaluate_window(window, ai_mark, player_mark)
            
    # Vertical
    for c in range(7):
        for r in range(3):
            window = [board[r+i][c] for i in range(4)]
            score += evaluate_window(window, ai_mark, player_mark)
            
    # Diagonal down-right
    for r in range(3):
        for c in range(4):
            window = [board[r+i][c+i] for i in range(4)]
            score += evaluate_window(window, ai_mark, player_mark)
            
    # Diagonal up-right
    for r in range(3, 6):
        for c in range(4):
            window = [board[r-i][c+i] for i in range(4)]
            score += evaluate_window(window, ai_mark, player_mark)
            
    return score


def c4_minimax(board, depth, alpha, beta, is_maximizing, ai_mark, player_mark):
    win = c4_check_win(board)
    if win == ai_mark:
        return 10000000 + depth
    elif win == player_mark:
        return -10000000 - depth
    elif win == "draw":
        return 0
    elif depth == 0:
        return evaluate_board(board, ai_mark)
        
    valid_cols = [c for c in range(7) if board[0][c] is None]
    
    if is_maximizing:
        value = -float('inf')
        for col in valid_cols:
            row = 0
            for r in range(5, -1, -1):
                if board[r][col] is None:
                    row = r
                    break
            board[row][col] = ai_mark
            score = c4_minimax(board, depth - 1, alpha, beta, False, ai_mark, player_mark)
            board[row][col] = None
            value = max(value, score)
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return value
    else:
        value = float('inf')
        for col in valid_cols:
            row = 0
            for r in range(5, -1, -1):
                if board[r][col] is None:
                    row = r
                    break
            board[row][col] = player_mark
            score = c4_minimax(board, depth - 1, alpha, beta, True, ai_mark, player_mark)
            board[row][col] = None
            value = min(value, score)
            beta = min(beta, value)
            if alpha >= beta:
                break
        return value


def get_c4_best_col(board, ai_mark, depth=4):
    valid_cols = [c for c in range(7) if board[0][c] is None]
    if not valid_cols:
        return None
    player_mark = "Y" if ai_mark == "R" else "R"
    
    # 1. Immediate Win check
    for col in valid_cols:
        row = 0
        for r in range(5, -1, -1):
            if board[r][col] is None:
                row = r
                break
        board[row][col] = ai_mark
        is_win = (c4_check_win(board) == ai_mark)
        board[row][col] = None
        if is_win:
            return col
            
    # 2. Block Opponent Win check
    for col in valid_cols:
        row = 0
        for r in range(5, -1, -1):
            if board[r][col] is None:
                row = r
                break
        board[row][col] = player_mark
        is_win = (c4_check_win(board) == player_mark)
        board[row][col] = None
        if is_win:
            return col

    # 3. Minimax
    best_score = -float('inf')
    best_col = valid_cols[0]
    for col in valid_cols:
        row = 0
        for r in range(5, -1, -1):
            if board[r][col] is None:
                row = r
                break
        board[row][col] = ai_mark
        score = c4_minimax(board, depth - 1, -float('inf'), float('inf'), False, ai_mark, player_mark)
        board[row][col] = None
        if score > best_score:
            best_score = score
            best_col = col
            
    return best_col


# ==========================================
# Pierre-Feuille-Ciseaux (RPS)
# ==========================================

class RPSGame:
    def __init__(self, score_a=0, score_b=0):
        self.score_a = score_a
        self.score_b = score_b
        
    def resolve_round(self, choice_a: str, choice_b: str) -> str:
        a = choice_a.lower().strip()
        b = choice_b.lower().strip()
        if a == b:
            return "draw"
        wins = {
            "pierre": "ciseaux",
            "feuille": "pierre",
            "ciseaux": "feuille"
        }
        if wins.get(a) == b:
            self.score_a += 1
            return "a"
        else:
            self.score_b += 1
            return "b"
            
    def winner(self) -> str | None:
        if self.score_a >= 2:
            return "a"
        if self.score_b >= 2:
            return "b"
        return None


# ==========================================
# Blackjack
# ==========================================

def create_deck(seed=None):
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    deck = ranks * 4
    rng = random.Random(seed)
    rng.shuffle(deck)
    return deck


class BlackjackGame:
    def __init__(self, seed=None):
        self.deck = create_deck(seed)
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        self.status = "playing"

    @staticmethod
    def hand_value(cards: list[str]) -> int:
        val = 0
        aces = 0
        for card in cards:
            if card in ['J', 'Q', 'K']:
                val += 10
            elif card == 'A':
                aces += 1
                val += 11
            else:
                val += int(card)
        while val > 21 and aces > 0:
            val -= 10
            aces -= 1
        return val

    def player_hit(self) -> str:
        if self.status != "playing":
            return self.status
        self.player_hand.append(self.deck.pop())
        if self.hand_value(self.player_hand) > 21:
            self.status = "player_bust"
        return self.status

    def player_stand(self) -> str:
        if self.status != "playing":
            return self.status
        self.status = "stand"
        while self.hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())
        self.status = "finished"
        return self.status

    def result(self) -> str:
        p_val = self.hand_value(self.player_hand)
        d_val = self.hand_value(self.dealer_hand)
        
        p_bj = (p_val == 21 and len(self.player_hand) == 2)
        d_bj = (d_val == 21 and len(self.dealer_hand) == 2)
        
        if p_bj and not d_bj:
            return "blackjack"
        if d_bj and not p_bj:
            return "dealer"
        if p_bj and d_bj:
            return "push"
            
        if p_val > 21:
            return "dealer"
        if d_val > 21:
            return "player"
            
        if p_val > d_val:
            return "player"
        elif d_val > p_val:
            return "dealer"
        else:
            return "push"


# ==========================================
# Quiz
# ==========================================

class QuizGame:
    def __init__(self, questions: list[dict], num_questions=5, seed=None):
        rng = random.Random(seed)
        self.questions = rng.sample(questions, min(len(questions), num_questions))
        self.current_index = 0
        self.score = 0

    def get_current_question(self) -> dict | None:
        if self.current_index < len(self.questions):
            return self.questions[self.current_index]
        return None

    def answer_question(self, choice_idx: int) -> bool:
        q = self.get_current_question()
        if not q:
            return False
        correct = (choice_idx == q["answer_idx"])
        if correct:
            self.score += 1
        self.current_index += 1
        return correct

    def is_finished(self) -> bool:
        return self.current_index >= len(self.questions)
