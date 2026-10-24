"""MemoryChallenge: a game (session tool). The game logic lives in game.py."""
from app.games import game_tool

from .game import MemoryChallenge

tool = game_tool(MemoryChallenge, emoji="🧠")
