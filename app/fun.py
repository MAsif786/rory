"""Personality for the bot: random, playful lines. Add variants freely."""
import random


def pick(lines: list[str], **kw) -> str:
    return random.choice(lines).format(**kw)


QUIT = [
    "👋 Rage quit? Fine, I'll remember this. 😤",
    "🏳️ Game over. Come back when you're ready for round two!",
    "💨 And just like that, you vanished. Later!",
]
CHEER = ["🎉 Boom!", "🔥 Nice one!", "😎 Smooth!", "🚀 Look at you go!", "💪 Brilliant!"]
OOPS = ["😬 Ouch.", "🙈 Not quite!", "😅 So close... or not.", "🤦 Oof."]

# Number guess
GUESS_RESET = ["🔄 New number locked in. Try me! 😈", "🎲 Rolled a fresh one. No peeking!"]
GUESS_WIN = [
    "🎉 YES! It was {n}! Got it in {tries} tries. Genius or lucky? 🤔",
    "🏆 {n}! Nailed it in {tries} guesses. I'm not even mad. (I'm a little mad.)",
    "🎯 Bullseye — {n} in {tries}! Send *play guess* for a rematch!",
]
GUESS_BAD = ["🧐 That's not a number. Try digits!", "🤨 Numbers only, champ."]
GUESS_RANGE = ["📏 Between {lo} and {hi}, please!", "🙃 Out of range! {lo}-{hi} only."]
HOT = "🔥 BURNING HOT"
WARM = "♨️ Warm"
COOL = "🌤️ Cool"
COLD = "🥶 Cold"

# Rock paper scissors
RPS_WIN = ["🎉 You win! Beginner's luck... 😒", "😤 You got me this time!", "🏆 Fine, you win. Rematch?"]
RPS_LOSE = ["😈 I win! Bow before me.", "🤖 Machine > human. Again?", "😏 Too easy!"]
RPS_DRAW = ["🤝 Draw! Great minds think alike.", "😮 Same move! Are you reading my mind?"]
RPS_BAD = ["🤔 Rock, paper or scissors. That's the whole game!", "😆 Not a legal move!"]

# Tic tac toe
TTT_WIN = ["🎉 You win! Okay, I let you. 😤", "🏆 Three in a row! I demand a rematch."]
TTT_LOSE = ["😈 I win! Three in a row, baby.", "🤖 Tic-tac-TOE-tally crushed you."]
TTT_DRAW = ["🤝 A draw! We're evenly matched... for now. 👀", "😮 Stalemate. Respect."]
TTT_TAKEN = ["🙅 Square {n} is taken! Pick another.", "👀 Nice try — {n} is already used!"]
TTT_BAD = ["🔢 Send a square 1-9!", "🤨 That's not on the board."]

# Hangman
HM_RIGHT = ["✅ '{c}' is in there!", "🎯 Yes! '{c}' fits.", "😎 '{c}' — nice guess!"]
HM_WRONG = ["❌ No '{c}' here.", "😬 '{c}'? Nope!", "🙈 Not '{c}'. Careful..."]
HM_WIN = ["🎉 You saved him! The word was *{w}*.", "🏆 Solved: *{w}*! Big brain."]
HM_LOSE = ["💀 Dead. The word was *{w}*. RIP.", "☠️ Game over! It was *{w}*."]
HM_REPEAT = ["🙄 You already tried '{c}'.", "🔁 '{c}' again? I'm not falling for it."]

# Memory
MEM_OK = ["✅ Perfect memory!", "🧠 Elephant brain!", "🔥 Not a single slip!"]
MEM_FAIL = ["❌ Whoops! Memory.exe stopped working.", "💥 Wrong! My goldfish remembers better."]
