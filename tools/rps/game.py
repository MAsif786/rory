import random

from app.fun import *
from app.games import Game

MOVES = {"rock": "✊", "paper": "✋", "scissors": "✌️"}
BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
ALIASES = {"r": "rock", "p": "paper", "s": "scissors"}


class RockPaperScissors(Game):
    key = "rps"
    title = "Rock Paper Scissors"
    order = 20
    aliases = ("rps", "rock paper scissors", "rock paper scissor", "rockpaperscissors", "rock paper", "janken", "roshambo")
    description = "Beat the bot. Send rock, paper or scissors."

    def __init__(self) -> None:
        self.wins = self.losses = self.draws = 0

    def start(self) -> str:
        return "✊✋✌️ Rock Paper Scissors! Send *rock*, *paper* or *scissors* (or r/p/s). Send *quit* to stop."

    def handle(self, text: str) -> str:
        text = text.strip().lower()
        mine = ALIASES.get(text, text)
        if mine not in MOVES:
            return pick(RPS_BAD)
        bot = random.choice(list(MOVES))
        if mine == bot:
            self.draws += 1
            result = pick(RPS_DRAW)
        elif BEATS[mine] == bot:
            self.wins += 1
            result = pick(RPS_WIN)
        else:
            self.losses += 1
            result = pick(RPS_LOSE)
        return (
            f"You: {MOVES[mine]} {mine}\nMe: {MOVES[bot]} {bot}\n{result}\n"
            f"Score — W {self.wins} · L {self.losses} · D {self.draws}"
        )
