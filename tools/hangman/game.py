import random
from pathlib import Path

from app.fun import *
from app.games import Game

WORDS = [w.strip().lower() for w in (Path(__file__).parent / "words.txt").read_text().splitlines() if w.strip()]
LIVES = 6


class Hangman(Game):
    key = "hangman"
    title = "Hangman"
    order = 40
    aliases = ("hangman", "hang man", "hangmen")
    description = "Guess the word"
    group_ok = True

    def __init__(self) -> None:
        self.word = random.choice(WORDS)
        self.guessed: list[str] = []
        self.lives = LIVES
        self._done = False

    def _masked(self) -> str:
        return " ".join(c if c in self.guessed else "_" for c in self.word)

    def _status(self) -> str:
        wrong = " ".join(c for c in self.guessed if c not in self.word) or "-"
        return f"{self._masked()}\n\n❤️ Lives: {self.lives}/{LIVES}\n❌ Wrong: {wrong}"

    def start(self) -> str:
        return f"🎯 {self.title}! The word has {len(self.word)} letters. Send a letter (or the whole word).\n\n{self._status()}\n\n*reset* new word · *quit* stop"

    def handle(self, text: str) -> str:
        text = text.strip().lower()
        if text == "reset":
            self.__init__()
            return f"🔄 New word.\n\n{self._status()}"
        if not text.isalpha():
            return "Send a letter, or guess the whole word. *reset* / *quit* also work."

        if len(text) > 1:  # whole-word guess
            if text == self.word:
                self._done = self.won = True
                return pick(HM_WIN, w=self.word) + " (*play hangman* to go again)"
            self.lives -= 1
        else:
            if text in self.guessed:
                return f"{pick(HM_REPEAT, c=text)}\n\n{self._status()}"
            self.guessed.append(text)
            if text in self.word:
                if all(c in self.guessed for c in self.word):
                    self._done = self.won = True
                    return pick(HM_WIN, w=self.word) + " (*play hangman* to go again)"
                return f"{pick(HM_RIGHT, c=text)}\n\n{self._status()}"
            self.lives -= 1

        if self.lives <= 0:
            self._done = True
            return pick(HM_LOSE, w=self.word) + " (*play hangman* to try again)"
        return f"{pick(HM_WRONG, c=text)}\n\n{self._status()}"

    @property
    def finished(self) -> bool:
        return self._done
