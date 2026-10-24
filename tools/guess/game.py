import random

from app.fun import *
from app.games import Game


class NumberGuess(Game):
    key = "guess"
    title = "Number Guess"
    order = 10
    aliases = ("number guess", "guess the number", "guess number", "guess a number", "guessing game", "number guessing game", "number game")
    ambiguous_aliases = ("guess", "number game")
    description = "Guess my secret number between 1 and 100."

    LOW, HIGH = 1, 100
    group_ok = True

    def __init__(self) -> None:
        self.secret = random.randint(self.LOW, self.HIGH)
        self.guesses: list[int] = []
        self._won = False

    def start(self) -> str:
        return (
            f"🎯 {self.title}: I picked a number between {self.LOW} and {self.HIGH}.\n"
            "Send a number to guess. Send *reset* for a new number or *quit* to stop."
        )

    def handle(self, text: str) -> str:
        text = text.strip().lower()
        if text == "reset":
            self.__init__()
            return pick(GUESS_RESET)
        if not text.lstrip("-").isdigit():
            return pick(GUESS_BAD) + " (or *reset* / *quit*)"
        n = int(text)
        if not self.LOW <= n <= self.HIGH:
            return pick(GUESS_RANGE, lo=self.LOW, hi=self.HIGH)
        self.guesses.append(n)
        if n == self.secret:
            self._won = self.won = True
            return pick(GUESS_WIN, n=n, tries=len(self.guesses))
        d = abs(n - self.secret)
        temp = HOT if d <= 3 else WARM if d <= 10 else COOL if d <= 25 else COLD
        hint = "higher ⬆️" if n < self.secret else "lower ⬇️"
        return f"{temp}! Go {hint} (guess #{len(self.guesses)})"

    @property
    def finished(self) -> bool:
        return self._won
