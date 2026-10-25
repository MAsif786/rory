"""Goal-driven people. Each persona wants something, types like a real person (not like the fixtures) and, when Rory does not get it,
rephrases the way people do. The score that matters is what a person feels: did I get it first time, or within three tries?

A persona is a goal (what the reply must contain), and an ordered list of things they would type: first attempt, then the rephrasings."""
import pytest

from tests.api_fixtures import routes
from tests.helpers import make_bot


class Persona:
    def __init__(self, name, goal, tries, first_try=False):
        self.name, self.goal, self.tries, self.first_try = name, goal, tries, first_try

    def __repr__(self):
        return self.name


# (who, what the reply must contain, what they type in order, must it work on the very first message?)
PERSONAS = [
    Persona("rushed commuter", ["Heads", "Tails"], ["flip", "toss a coin"], first_try=True),
    Persona("typo-prone student", "28,050", ["100 usd to pkr", "convert 100 usd to pkr"], first_try=True),
    Persona("shouting user", ["Heads", "Tails"], ["FLIP A COIN!!!"], first_try=True),
    Persona("polite aunt", ["Heads", "Tails"], ["hello rory, could you please flip a coin for me, thank you"], first_try=True),
    Persona("texting teenager", ["Heads", "Tails"], ["yo flip a coin pls 😂"], first_try=True),
    Persona("autocorrect victim", ["Heads", "Tails"], ["flipp a coin", "fip a coin", "flip a coin"], first_try=False),
    Persona("dice gamer", "You rolled", ["rol a dice", "roll a dice"], first_try=False),
    Persona("curious kid", "Did you know", ["fun fct", "tell me a fun fact"], first_try=False),
    Persona("impatient asker", "You rolled", ["roll", "roll a dice"], first_try=True),
]


@pytest.mark.parametrize("p", PERSONAS, ids=repr)
async def test_a_person_gets_what_they_came_for(p):
    bot, http = make_bot(routes())
    goals = [p.goal] if isinstance(p.goal, str) else p.goal
    replies = []
    for typed in p.tries:
        reply = await bot.respond("chat", typed)
        replies.append((typed, reply))
        if any(g in reply for g in goals):
            break
    got = [i for i, (_, r) in enumerate(replies, 1) if any(g in r for g in goals)]
    assert got, f"{p.name} never got {goals}: {replies}"
    assert got[0] <= 3, f"{p.name} needed {got[0]} tries"
    if p.first_try:
        assert got[0] == 1, f"{p.name} should succeed first time but typed {replies[0][0]!r} and got: {replies[0][1]!r}"
