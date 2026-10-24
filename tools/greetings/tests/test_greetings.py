from datetime import datetime

import pytest

from app.core.context import ContextStore
from app.core.dispatcher import Dispatcher
from app.core.registry import Registry
from app.intent.rule_based import decide
from app.smart import Bot
from tools.greetings import tool as mod


@pytest.fixture
def bot(monkeypatch):
    mod._last.clear()
    reg = Registry()
    reg.add(mod.tool, "greetings")
    return Bot(reg, Dispatcher(reg), decide, ContextStore())


def at(monkeypatch, hour):
    monkeypatch.setattr(mod, "_now", lambda: datetime(2026, 10, 25, hour))


@pytest.mark.parametrize("hour, word", [(6, "morning"), (13, "afternoon"), (19, "evening"), (23, "night"), (2, "night")])
def test_daypart(hour, word):
    assert mod.daypart(hour) == word


@pytest.mark.parametrize("hour, expected", [(8, "Morning"), (14, "afternoon"), (20, "evening"), (1, "🌙")])
async def test_hello_follows_the_time_of_day(bot, monkeypatch, hour, expected):
    at(monkeypatch, hour)
    out = await bot.handle("c", "hi")
    assert expected.lower() in out.lower() and "I'm Rory" in out and "*help*" in out


async def test_greeting_again_changes_tone_and_drops_the_hint(bot, monkeypatch):
    at(monkeypatch, 9)
    await bot.handle("c", "hello")
    again = await bot.handle("c", "hey")
    assert "again" in again.lower() or "back" in again.lower()
    assert "*help*" not in again
    assert "I'm Rory" in await bot.handle("other chat", "hello")                   # per chat


async def test_bye_resets_so_the_next_hello_is_a_fresh_one(bot, monkeypatch):
    at(monkeypatch, 9)
    await bot.handle("c", "hello")
    await bot.handle("c", "bye")
    assert "I'm Rory" in await bot.handle("c", "hello")


async def test_salam_gets_the_proper_reply(bot):
    for text in ("assalamualaikum", "Assalam o Alaikum", "salam", "AOA"):
        assert (await bot.handle("c", text)).startswith("Wa alaikum assalam")


async def test_good_part_of_day(bot, monkeypatch):
    at(monkeypatch, 9)
    assert (await bot.handle("c", "good morning")).startswith("Good morning!")
    assert "It's morning here" in await bot.handle("c", "good evening")
    assert "Sleep well" in await bot.handle("c", "good night")
    assert (await bot.handle("c", "morning")).startswith("Good morning")


async def test_small_talk(bot):
    assert "Rory" in await bot.handle("c", "who are you")
    assert "Rory" in await bot.handle("c", "tell me about yourself")
    assert await bot.handle("c", "thank you so much")
    assert await bot.handle("c", "how are you?")
    assert await bot.handle("c", "good bot")
    assert await bot.handle("c", "bye")
