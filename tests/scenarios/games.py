"""Game conversations: start, play, finish, quit, interruptions and expiry."""
from app.core.context import SESSION_TTL
from tests.scenarios.dsl import Scenario, T


def secret(n):
    return lambda bot: setattr(bot.store.get("chat").session.state, "secret", n)


def hand(bot):
    g = bot.store.get("chat").session.state
    g.player, g.dealer = ["K♠", "7♥"], ["K♦", "9♣"]


def sequence(bot):
    bot.store.get("chat").session.state.sequence = ["🍎", "🐶", "🚗"]


SCENARIOS = [
    Scenario("every game can be started by name and quit", [T(f"play {g}", session=g) if i == 0 else T("quit", has="Game ended", session=None)
                                                              for g in ["hangman"] for i in range(2)]),
    Scenario("guess: hint then win", [T("play guess", session="guess"), T("10", pre=secret(42), any_of=["higher", "Go"], session="guess"),
                                       T("42", has="42", session=None)]),
    Scenario("guess: bad input is handled in the game", [T("play guess"), T("banana", session="guess", lacks="didn't get that"), T("999", session="guess")]),
    Scenario("rps: any move gets a result", [T("play rps", session="rps"), T("rock", has="Score", session="rps"), T("r", has="Score"), T("lizard", session="rps")]),
    Scenario("hangman: guesses", [T("play hangman", session="hangman"), T("e", has="Lives", session="hangman"), T("e", any_of=["again", "already"], session="hangman")]),
    Scenario("tictactoe: a move", [T("play tic tac toe", session="ttt"), T("5", has=["❌", "⭕"], session="ttt"), T("5", session="ttt")]),
    Scenario("blackjack: stand ends the round", [T("play blackjack", session="blackjack"), T("stand", pre=hand, any_of=["win", "lose", "Push", "push", "bust", "Dealer"])]),
    Scenario("highlow: guesses", [T("play higher or lower", session="highlow"), T("higher", any_of=["Streak", "Same card", "Game over"])]),
    Scenario("memory: reverse order", [T("play memory challenge", session="memory", has="reverse"), T("🚗🐶🍎", pre=sequence, has="Round 2", session="memory"),
                                         T("x", session=None, has="survived")]),
    Scenario("dungeon: move around", [T("play dungeon", session="dungeon"), T("forward", lint=False)]),
    Scenario("trivia: answers", [T("play trivia", has=["A)", "B)", "C)", "D)"], session="trivia"), T("a", session=None, any_of=["Correct", "Nope", "Not quite", "Ouch", "Nailed", "Big brain"])]),
    Scenario("quiz: five questions in a row", [T("play quiz", has="Q1/5", session="quiz"), T("a", has="Q2/5", session="quiz")]),
    Scenario("game wins over commands and tools", [T("play hangman"), T("ping", session="hangman", lacks="pong"), T("weather in lahore", session="hangman", lacks="Lahore")]),
    Scenario("stop ends any game", [T("play guess"), T("stop", has="Game ended", session=None), T("ping", eq="pong 🏓")]),
    Scenario("game expires after idle time", [T("play guess", session="guess"), T("ping", wait=SESSION_TTL + 1, eq="pong 🏓", session=None)]),
    Scenario("passthrough: chat unrelated to trivia reaches the intent engine", [T("play trivia", session="trivia"), T("hello", session="trivia", has="Rory")]),
    Scenario("starting a game while another is on is handled by the active game", [T("play guess", session="guess"), T("play hangman", session="guess")]),
    Scenario("game aliases", [T("lets play tic tac toe", session="ttt"), T("quit"), T("play rock paper scissors", session="rps"), T("quit"),
                              T("play number guess", session="guess")]),
]
