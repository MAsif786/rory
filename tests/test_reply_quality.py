"""Quality bar for every answer the bot can give, using realistic upstream data: well formed, scannable on a phone, and not an error."""
import re

import pytest

from tests import api_fixtures as F
from tests.helpers import lint_reply, make_bot, real_registry

REG = real_registry()
CASES = [(s.full_name, ex) for s in REG.specs() if s.tool != "link" for ex in s.examples]
ERRORS = ("Something went wrong", "couldn't reach", "didn't get that", "isn't set up")
OPERATOR_ONLY = ("API_KEY", "API key", ".env", "GOOGLE_", "TMDB", "GITHUB_TOKEN", "BOT_CONTACT", "NEWS_COUNTRY", "environment variable")
MAX_LINES, MAX_LINE = 40, 300


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_CSE_ID", "c")


@pytest.mark.parametrize("feature, example", CASES, ids=[f"{f}:{e}" for f, e in CASES])
async def test_reply_is_clean_scannable_and_not_an_error(feature, example):
    bot, _ = make_bot(F.routes())
    reply = await bot.respond("c", example)
    assert not lint_reply(reply), reply
    assert not any(e in reply for e in ERRORS), f"{example!r} -> error reply:\n{reply}"
    assert not any(w in reply for w in OPERATOR_ONLY), f"{example!r} shows server configuration to the user:\n{reply}"
    lines = reply.split("\n")
    assert len(lines) <= MAX_LINES, f"{len(lines)} lines is too long to read on a phone"
    long = [l for l in lines if len(l) > MAX_LINE and "http" not in l]
    assert not long, f"lines too long to read comfortably: {long[:2]}"


@pytest.mark.parametrize("feature, example", [c for c in CASES if c[0].split(".")[0] not in {"greetings", "dice"}], ids=lambda v: None)
async def test_answers_open_with_a_title_line_not_a_wall_of_text(feature, example):
    """Answer replies start with an emoji (the visual anchor in a chat list) and the first line stays short."""
    bot, _ = make_bot(F.routes())
    first = (await bot.respond("c", example)).split("\n")[0]
    assert not first[0].isalnum(), f"{feature}: first line should open with an emoji, got {first!r}"
    assert len(first) <= 160, f"{feature}: first line is {len(first)} chars; keep the headline short"


async def test_numbers_are_formatted_for_humans():
    bot, _ = make_bot(F.routes())
    assert "28,050.00" in await bot.respond("c", "100 usd to pkr")                  # thousands separators, 2 decimals
    assert "125,000,000" in await bot.respond("c", "capital of japan")


async def test_every_menu_and_help_page_is_clean():
    bot, _ = make_bot({})
    pages = ["help", "menu", "help all", "games", *[f"help {t}" for t in REG.tools], *[f"help {s.full_name}" for s in REG.specs()], "help nope"]
    for page in pages:
        reply = await bot.respond("c", page)
        assert not lint_reply(reply), f"{page!r}: {lint_reply(reply)}\n{reply}"
        assert len(reply) < 6000, f"{page!r} is {len(reply)} chars"


async def test_no_reply_ever_tells_users_how_to_configure_the_server(monkeypatch):
    """Optional keys (TMDB, GitHub, Google...) are unset by default: every tool must still answer without mentioning them."""
    for key in ("GOOGLE_API_KEY", "GOOGLE_CSE_ID", "TMDB_API_KEY", "GITHUB_TOKEN", "BOT_CONTACT", "NEWS_COUNTRY"):
        monkeypatch.delenv(key, raising=False)
    bot, _ = make_bot(F.routes())
    for feature, example in CASES:
        reply = await bot.respond("c", example)
        assert not any(w in reply for w in OPERATOR_ONLY), f"{feature}: {example!r} shows server configuration:\n{reply}"
