"""Higher or Lower: guess if the next card is higher or lower."""
import random

from app.games import Game


class HigherLower(Game):
    key = "highlow"
    title = "Higher or Lower"
    order = 65
    aliases = ("higher or lower", "higher lower", "hi lo", "high low", "hilo", "higher or lower game")
    description = "Higher or lower card"
    group_ok = False

    TARGET = 5

    def __init__(self) -> None:
        self.card = random.randint(2, 14)
        self.streak = 0
        self._done = False

    @staticmethod
    def _name(v: int) -> str:
        return {11: "J", 12: "Q", 13: "K", 14: "A"}.get(v, str(v))

    def start(self) -> str:
        return (f"🃏 *Higher or Lower* — reach {self.TARGET} correct in a row.\n\n"
                f"Current card: *{self._name(self.card)}*\nSend *higher* or *lower* (or *h* / *l*). *quit* to stop.")

    def handle(self, text: str) -> str:
        guess = {"h": "higher", "higher": "higher", "up": "higher", "l": "lower", "lower": "lower", "down": "lower"}.get(text.strip().lower())
        if not guess:
            return "Send *higher* or *lower*."
        nxt = random.randint(2, 14)
        if nxt == self.card:
            msg = f"🤝 Same card ({self._name(nxt)}) — no change."
        elif (nxt > self.card) == (guess == "higher"):
            self.streak += 1
            msg = f"✅ {self._name(nxt)}! Streak: {self.streak}/{self.TARGET}"
        else:
            self._done = True
            return f"❌ It was *{self._name(nxt)}*. Game over at a streak of {self.streak}. Say *higher or lower* to play again."
        self.card = nxt
        if self.streak >= self.TARGET:
            self._done = self.won = True
            return f"🏆 {self.TARGET} in a row! You win. Say *higher or lower* for another round."
        return f"{msg}\nCurrent card: *{self._name(self.card)}* — higher or lower?"

    @property
    def finished(self) -> bool:
        return self._done
