"""Failure matrix: every answer feature x every way an upstream service can fail.

The contract: the user always gets a short, friendly, well-formed reply. Never a traceback, never silence, never a raw API message,
and a failure must not break the next message. Outages say so ("couldn't reach that service"); odd data gets a friendly message or the
generic error. Pure tools (calculator, dice, ...) must be unaffected by an outage."""
import time

import pytest

from app.core.dispatcher import GENERIC_ERROR, NETWORK_ERROR, Dispatcher
from app.core.context import ContextStore
from app.intent.rule_based import decide
from app.smart import Bot
from tests import api_fixtures as F
from tests.helpers import FakeHttp, lint_reply, make_bot, real_registry

from types import SimpleNamespace

REG = real_registry()
# link previews fetch pages with their own hardened client (not ctx.services.http); they are covered by the live tests
CASES = [(s.full_name, ex) for s in REG.specs() if s.kind == "answer" and s.tool != "link" for ex in s.examples[:1]]
OUTAGES = ["connect", "timeout", "500"]
BAD_DATA = ["404", "malformed", "empty"]
LEAKS = ("Traceback", "Error:", "Exception", "httpx", "status code", "upstream says no", "unexpected", "Client error", "Server error")


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_CSE_ID", "c")


async def ask(example, fail=None):
    bot, http = make_bot(F.routes(), fail=fail)
    return await bot.respond("c", example), http, bot


async def uses_network(example) -> bool:
    _, http, _ = await ask(example)
    return bool(http.calls)


@pytest.mark.parametrize("feature, example", CASES, ids=[f for f, _ in CASES])
@pytest.mark.parametrize("mode", OUTAGES)
async def test_outage_gives_a_clear_message(feature, example, mode):
    reply, _, _ = await ask(example, mode)
    assert not lint_reply(reply), reply
    if await uses_network(example):
        assert reply == NETWORK_ERROR, f"{feature} on {mode!r} replied:\n{reply}"
    else:
        assert "went wrong" not in reply and "couldn't reach" not in reply          # a pure tool shrugs the outage off


@pytest.mark.parametrize("feature, example", CASES, ids=[f for f, _ in CASES])
@pytest.mark.parametrize("mode", BAD_DATA)
async def test_bad_upstream_data_is_handled(feature, example, mode):
    reply, _, _ = await ask(example, mode)
    assert not lint_reply(reply), reply
    assert not any(leak in reply for leak in LEAKS), f"{feature} leaked internals on {mode!r}:\n{reply}"
    assert len(reply) < 400, "an error reply should be short"


@pytest.mark.parametrize("feature, example", CASES, ids=[f for f, _ in CASES])
async def test_a_failure_does_not_break_the_next_message(feature, example):
    bot, http = make_bot(F.routes(), fail="connect")
    await bot.respond("c", example)
    http.fail = None
    again = await bot.respond("c", example)
    assert not lint_reply(again) and "couldn't reach" not in again and "went wrong" not in again, again


@pytest.mark.parametrize("feature, example", [c for c in CASES if c[0].split(".")[0] not in {"calc", "dice", "units", "greetings", "clock"}],
                         ids=lambda v: v if isinstance(v, str) and "." in v else None)
async def test_a_hung_upstream_times_out_quickly(feature, example):
    http = FakeHttp(F.routes(), fail="slow")
    bot = Bot(REG, Dispatcher(REG, timeout=0.2), decide, ContextStore(), SimpleNamespace(http=http))
    start = time.perf_counter()
    reply = await bot.respond("c", example)
    assert time.perf_counter() - start < 3, "the bot hung on a stalled upstream"
    assert reply == GENERIC_ERROR and not lint_reply(reply)


async def test_trivia_still_starts_without_the_internet():
    """Trivia has an offline question bank: an outage must not stop a game from starting."""
    reply, _, bot = await ask("play trivia", "connect")
    assert "A)" in reply and bot.store.get("c").session.tool == "trivia"
    reply, _, _ = await ask("play quiz", "500")
    assert "Q1/5" in reply


async def test_outage_replies_are_never_remembered_for_repeats():
    bot, http = make_bot(F.routes(), fail="connect")
    assert await bot.respond("c", "capital of japan") == NETWORK_ERROR
    http.fail = None
    assert "Tokyo" in await bot.respond("c", "capital of japan")                    # not 'Same as a moment ago: <error>'


async def test_a_slow_trivia_api_falls_back_to_the_offline_bank_quickly(monkeypatch):
    from tools.trivia import game
    monkeypatch.setattr(game, "QUESTION_TIMEOUT", 0.1)
    http = FakeHttp(F.routes(), fail="slow")
    bot = Bot(REG, Dispatcher(REG), decide, ContextStore(), SimpleNamespace(http=http))
    start = time.perf_counter()
    reply = await bot.respond("c", "play trivia")
    assert time.perf_counter() - start < 2 and "A)" in reply


@pytest.mark.parametrize("query", ["google einstein", "search for best pizza in lahore", "google zzzqqq nothing here"])
async def test_unconfigured_web_search_never_shows_setup_instructions(query, monkeypatch):
    """Missing server configuration is the operator's problem: users get an answer or a plain 'nothing found', never .env / API-key text."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)
    for fail in (None, "connect", "empty", "malformed"):
        bot, _ = make_bot(F.routes(), fail=fail)
        reply = await bot.respond("c", query)
        assert not lint_reply(reply) and not any(w in reply for w in ("GOOGLE", ".env", "API key", "set up", "programmablesearchengine")), reply
