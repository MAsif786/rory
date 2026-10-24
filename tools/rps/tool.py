"""RockPaperScissors: a game (session tool). The game logic lives in game.py."""
from app.games import game_tool

from .game import RockPaperScissors

tool = game_tool(RockPaperScissors, emoji="✊")
