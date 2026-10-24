"""Dice: coin, dice and decisions."""
import random
import re

from app.core.schemas import Input, UserError
from app.core.tool import Tool

tool = Tool("dice", title="Dice", emoji="🎲", description="Coin, dice and decisions")


@tool.feature(
    "flip", description="Flip a coin",
    phrases=["flip a coin", "flip coin", "toss a coin", "toss coin", "coin flip", "coin toss", "heads or tails", "flip the coin",
             "toss the coin", "coin"],
    examples=["flip a coin", "heads or tails"])
async def flip(ctx):
    return random.choice(["🪙 *Heads!*", "🪙 *Tails!*"])


@tool.feature(
    "roll", description="Roll dice (default one 6-sided die; try 2d6 or d20)",
    phrases=["roll {dice}", "roll a dice", "roll a die", "roll the dice", "roll dice", "throw a dice", "throw the dice", "dice", "die"],
    examples=["roll a dice", "roll 2d6"],
    negatives=["roll call", "roll back", "roll out", "rock and roll"],
    inputs={"dice": Input(pattern=r"\d{0,2}d\d{1,3}")})
async def roll(ctx, dice):
    n, sides = 1, 6
    if dice:
        m = re.match(r"^(\d{1,2})?d(\d{1,3})$", dice, re.I)
        n, sides = int(m.group(1) or 1), int(m.group(2))
    if not 1 <= n <= 20 or not 2 <= sides <= 1000:
        raise UserError("🎲 Between 1 and 20 dice, with 2 to 1000 sides each.")
    rolls = [random.randint(1, sides) for _ in range(n)]
    detail = f" ({' + '.join(map(str, rolls))})" if n > 1 else ""
    return f"🎲 *{sum(rolls)}*{detail}  — {n}d{sides}"


@tool.feature(
    "choose", description="Pick one option for you (choose pizza, sushi or tacos)",
    phrases=["choose {options}", "choose between {options}", "choose from {options}", "pick {options}", "pick between {options}",
             "decide {options}", "decide between {options}"],
    keywords=["choose", "decide"],
    examples=["choose between pizza or sushi", "pick pizza, sushi, tacos"],
    inputs={"options": Input(required=True, pattern=r".+(?:,|\bor\b|/).+",
                             ask="🤔 Which options should I pick from? (e.g. *pizza, sushi or tacos*)")})
async def choose(ctx, options):
    picks = [o.strip() for o in re.split(r"\s*(?:,|\bor\b|/)\s*", options) if o.strip()]
    if len(picks) < 2:
        raise UserError("🤔 Give me at least two options, e.g. *choose pizza, sushi*.")
    return f"🎯 I pick: *{random.choice(picks)}*"
