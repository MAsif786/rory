"""NumberGuess: a game (session tool). The game logic lives in game.py."""
from app.games import game_tool

from .game import NumberGuess

tool = game_tool(NumberGuess, emoji="🎯")
