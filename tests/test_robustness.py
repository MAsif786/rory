"""Whatever arrives over the wire, the bot answers with a clean string, quickly, and keeps working."""
import random
import string
import time

import pytest

from tests import api_fixtures as F
from tests.helpers import lint_reply, make_bot

SEED = 20261025
ALPHABETS = [string.ascii_letters + string.digits + " ", string.punctuation + " ", "🙂😂👍🔥🇵🇰 ", "اردو عربى نص مختلط ", "​‍﻿\t\r\n ",
             "weather in lahore forecast news about 100 usd to pkr play who is "]


def random_messages(n=300):
    rng = random.Random(SEED)
    for _ in range(n):
        alphabet = rng.choice(ALPHABETS)
        yield "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 120)))


WEIRD = ["", " ", "\n\n\n", "   \t  ", ".", "?", "!!!", "\x00", "\x00weather in lahore", "weather in lahore\x00", "á" * 50, "😀" * 500, "ا" * 400,
         "NULL", "None", "undefined", "{}", "[]", "{place}", "%s %d", "${jndi:ldap://x}", "'; DROP TABLE users;--", "<script>alert(1)</script>",
         "../../etc/passwd", "weather in " + "x" * 3000, "100 usd to " + "p" * 2000, "play " * 400, "\\", "(", ")))", "[[[", "*", "**bold**", "_", "~",
         "whatsapp://send?text=hi", "https://", "http://" + "a" * 2500, "9" * 400, "-" * 300, "1/0", "0/0", "9**9**9", "sqrt(-1)", "log(0)"]


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_CSE_ID", "c")


@pytest.mark.parametrize("text", WEIRD, ids=[repr(w[:24]) for w in WEIRD])
async def test_odd_messages_get_a_clean_reply(text):
    bot, _ = make_bot(F.routes())
    start = time.perf_counter()
    reply = await bot.respond("c", text)
    assert time.perf_counter() - start < 2
    assert isinstance(reply, str) and reply.strip()
    assert "Traceback" not in reply and "Error" not in reply.replace("error", "")


async def test_three_hundred_random_messages_never_crash_or_hang():
    bot, _ = make_bot(F.routes())
    start = time.perf_counter()
    for text in random_messages():
        reply = await bot.respond("fuzz", text)
        assert isinstance(reply, str) and reply.strip(), repr(text)
        assert len(reply) < 6000, repr(text)
        assert "Traceback" not in reply, repr(text)
    assert time.perf_counter() - start < 20


async def test_bot_keeps_working_after_garbage():
    bot, _ = make_bot(F.routes())
    for text in WEIRD:
        await bot.respond("c", text)
    assert "pong" in await bot.respond("c", "ping")
    assert "*200*" in await bot.respond("c", "25*8")


async def test_one_chat_cannot_affect_another():
    bot, _ = make_bot(F.routes())
    await bot.respond("alice", "play hangman")
    await bot.respond("bob", "weather")                                            # bob has a pending question
    assert bot.store.get("alice").session and not bot.store.get("bob").session
    assert "pong" in await bot.respond("bob", "ping")
    assert bot.store.get("alice").pending is None and bot.store.get("bob").pending is not None
    assert "Lahore" in await bot.respond("bob", "lahore")                         # bob's answer completes bob's question only
    assert bot.store.get("alice").session


async def test_replies_to_many_chats_stay_isolated_under_interleaving():
    bot, http = make_bot(F.routes())
    chats = [f"chat{i}" for i in range(20)]
    for c in chats:
        await bot.respond(c, "weather")
    for c in reversed(chats):
        assert "Lahore" in await bot.respond(c, "multan")
    assert all(bot.store.get(c).pending is None for c in chats)
