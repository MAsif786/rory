import random

from app.fun import pick
from app.games import Game

SUITS = "♠♥♦♣"
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def value(hand: list[str]) -> int:
    total = sum(10 if r[:-1] in ("J", "Q", "K") else 11 if r[:-1] == "A" else int(r[:-1]) for r in hand)
    aces = sum(r[:-1] == "A" for r in hand)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def draw() -> str:
    return random.choice(RANKS) + random.choice(SUITS)


class Blackjack(Game):
    key = "blackjack"
    title = "Blackjack"
    order = 90
    aliases = ("blackjack", "black jack", "bj", "21", "twenty one", "twenty-one", "card game", "cards")
    ambiguous_aliases = ("bj", "21", "twenty one", "twenty-one", "cards")
    description = "Beat the dealer to 21"
    points = 15

    def __init__(self) -> None:
        self.player = [draw(), draw()]
        self.dealer = [draw(), draw()]
        self._done = False

    def _table(self, hide: bool = True) -> str:
        d = f"{self.dealer[0]} 🂠" if hide else " ".join(self.dealer)
        dv = "?" if hide else value(self.dealer)
        return f"🃏 Dealer: {d}  ({dv})\n🙂 You: {' '.join(self.player)}  ({value(self.player)})"

    def start(self) -> str:
        if value(self.player) == 21:
            return self._finish(blackjack=True)
        return f"♠️ *Blackjack*\n\n{self._table()}\n\nSend *hit* or *stand*. (*quit* to stop)"

    def _finish(self, blackjack: bool = False) -> str:
        self._done = True
        while value(self.dealer) < 17 and not blackjack:
            self.dealer.append(draw())
        p, d = value(self.player), value(self.dealer)
        if blackjack:
            self.won = True
            verdict = "🎰 *BLACKJACK!* Natural 21 — you win!"
        elif p > 21:
            verdict = "💥 Bust! Dealer wins."
        elif d > 21:
            self.won = True
            verdict = "🎉 Dealer busts — you win!"
        elif p > d:
            self.won = True
            verdict = "🏆 You win!"
        elif p < d:
            verdict = "😈 Dealer wins."
        else:
            verdict = "🤝 Push — it's a tie."
        return f"{self._table(hide=False)}\n\n{verdict}\n(*play blackjack* to play again)"

    def handle(self, text: str) -> str:
        t = text.strip().lower()
        if t in ("hit", "h"):
            self.player.append(draw())
            if value(self.player) >= 21:
                return self._finish()
            return f"{self._table()}\n\n*hit* or *stand*?"
        if t in ("stand", "s", "stay"):
            return self._finish()
        return "Send *hit* or *stand* (or *quit*)."

    @property
    def finished(self) -> bool:
        return self._done
