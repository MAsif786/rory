"""Quiz: five trivia questions in a row. Shares its logic with the trivia tool."""
from app.games import game_tool
from tools.trivia.game import Quiz

tool = game_tool(Quiz, emoji="📝")
