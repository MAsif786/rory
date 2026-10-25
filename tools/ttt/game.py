import random

from app.fun import *
from app.games import Game

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
NUMS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


def winner(b: list[str]) -> str | None:
    for a, c, d in LINES:
        if b[a] and b[a] == b[c] == b[d]:
            return b[a]
    return None


class TicTacToe(Game):
    key = "ttt"
    title = "Tic-Tac-Toe"
    order = 30
    aliases = ("ttt", "tictactoe", "tic tac toe", "tic-tac-toe", "tic tac", "tik tak toe", "tic tak toe", "xo", "xox", "x o", "noughts and crosses", "naughts and crosses", "x and o", "xs and os")
    ambiguous_aliases = ("xo", "x o")
    description = "Play against the bot"

    def __init__(self) -> None:
        self.board = [""] * 9
        self._done = False

    def render(self) -> str:
        cells = [{"X": "❌", "O": "⭕"}.get(c, NUMS[i]) for i, c in enumerate(self.board)]
        return "\n".join("".join(cells[r * 3:r * 3 + 3]) for r in range(3))

    def start(self) -> str:
        return f"❌⭕ *{self.title}* — you're ❌. Send a square number 1-9.\n\n{self.render()}\n\n*reset* restarts, *quit* stops."

    def _bot_move(self) -> int:
        free = [i for i, c in enumerate(self.board) if not c]
        for mark in ("O", "X"):  # win first, then block
            for i in free:
                self.board[i] = mark
                hit = winner(self.board) == mark
                self.board[i] = ""
                if hit:
                    return i
        if 4 in free:
            return 4
        return random.choice(free)

    def handle(self, text: str) -> str:
        text = text.strip().lower()
        if text == "reset":
            self.__init__()
            return f"🔄 New game.\n\n{self.render()}"
        if not text.isdigit() or not 1 <= int(text) <= 9:
            return pick(TTT_BAD) + " (or *reset* / *quit*)"
        i = int(text) - 1
        if self.board[i]:
            return f"{pick(TTT_TAKEN, n=text)}\n\n{self.render()}"

        self.board[i] = "X"
        if winner(self.board):
            self._done = self.won = True
            return f"{self.render()}\n\n{pick(TTT_WIN)} (*play ttt* to go again)"
        if all(self.board):
            self._done = True
            return f"{self.render()}\n\n{pick(TTT_DRAW)} (*play ttt* to go again)"

        self.board[self._bot_move()] = "O"
        if winner(self.board):
            self._done = True
            return f"{self.render()}\n\n{pick(TTT_LOSE)} (*play ttt* to go again)"
        if all(self.board):
            self._done = True
            return f"{self.render()}\n\n{pick(TTT_DRAW)} (*play ttt* to go again)"
        return self.render()

    @property
    def finished(self) -> bool:
        return self._done
