import random

from app.fun import *
from app.games import Game

POOL = ["🍎", "🐶", "🚗", "⭐", "🎈", "🍕", "🐱", "🌙", "🔥", "🎸", "🌵", "🦋"]
START_LEN = 3


class MemoryChallenge(Game):
    key = "memory"
    title = "Memory Challenge"
    order = 50
    aliases = ("memory challenge", "memory game", "emoji memory", "memory test", "remember game", "memory")
    ambiguous_aliases = ("memory",)
    description = "Repeat the emoji sequence"

    def __init__(self) -> None:
        self.round = 0
        self.sequence: list[str] = []
        self._done = False

    def _next_round(self) -> str:
        self.round += 1
        n = START_LEN + self.round - 1
        # later rounds draw from a bigger pool, so they get harder in two ways
        pool = POOL[: min(len(POOL), 6 + self.round)]
        self.sequence = [random.choice(pool) for _ in range(n)]
        return f"🧠 Round {self.round} — memorize, then send it *in reverse order*:\n\n{' '.join(self.sequence)}"

    def start(self) -> str:
        return "🧩 *Memory Challenge*: I'll show some emojis. Send them back in *reverse* order. Each round adds one more. *quit* to stop.\n\n" + self._next_round()

    @staticmethod
    def _parse(text: str) -> list[str]:
        return [c for c in text if not c.isspace() and c != "️"]

    def handle(self, text: str) -> str:
        if text.strip().lower() == "reset":
            self.__init__()
            return self.start()
        guess = self._parse(text)
        expected = self._parse("".join(reversed(self.sequence)))
        if not guess:
            return "Send the emoji sequence, or *reset* / *quit*."
        if guess == expected:
            return f"{pick(MEM_OK)}\n\n{self._next_round()}"
        self._done = True
        return (
            f"{pick(MEM_FAIL)} It was:\n{' '.join(self.sequence)}\n\n"
            f"You survived {self.round - 1} round(s). *play memory* to try again."
        )

    @property
    def finished(self) -> bool:
        return self._done
