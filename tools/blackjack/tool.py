"""Blackjack: a game (session tool). The game logic lives in game.py."""
from app.games import game_tool

from .game import Blackjack

tool = game_tool(Blackjack, emoji="🃏")
