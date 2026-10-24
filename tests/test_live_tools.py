"""Smoke tests against the REAL upstream APIs. Skipped by default; run them to find out whether a tool is broken right now:

    .venv/bin/python -m pytest -m live -q            # all tools
    .venv/bin/python -m pytest -m live -q -k weather # one tool

A failure here with green offline tests means the outside world changed (API shape, outage, rate limit, new auth rule)."""
import os
import time

import pytest

from app.intent.rule_based import decide
from tests.helpers import lint_reply, real_registry
from app.core.context import ContextStore
from app.core.dispatcher import Dispatcher
from app.smart import Bot
from app.core.services import Services

pytestmark = pytest.mark.live
REG = real_registry()
ERRORS = ("Something went wrong", "couldn't reach", "didn't get that")
NEEDS_KEY = {"search.web": ("GOOGLE_API_KEY", "GOOGLE_CSE_ID")}
# one example per feature is enough to prove the endpoint still works; session features (games) are covered too: their first reply
CASES = [(s.full_name, s.examples[0]) for s in REG.specs() if s.examples]
SLOW_SECONDS = 8


def _args_of(example):
    return [v for v in decide(example, REG.specs()).args.values() if isinstance(v, str) and len(v) >= 3]


@pytest.fixture
async def live_bot():
    services = Services()
    yield Bot(REG, Dispatcher(REG), decide, ContextStore(), services)
    if services._http:
        await services._http.aclose()


@pytest.mark.parametrize("feature, example", CASES, ids=[f"{f}" for f, _ in CASES])
async def test_tool_works_against_the_real_api(feature, example, live_bot):
    if missing := [k for k in NEEDS_KEY.get(feature, ()) if not os.getenv(k)]:
        pytest.skip(f"needs {', '.join(missing)} in the environment")
    start = time.perf_counter()
    reply = await live_bot.respond("live", example)
    took = time.perf_counter() - start
    assert not any(e in reply for e in ERRORS), f"{feature}: {example!r} -> {reply}"
    assert not lint_reply(reply), f"{feature}: {lint_reply(reply)}\n{reply}"
    assert took < SLOW_SECONDS, f"{feature} took {took:.1f}s (budget {SLOW_SECONDS}s)"


@pytest.mark.parametrize("feature, example", [c for c in CASES if c[0].split(".")[0] in {"weather", "wiki", "country", "currency", "github", "ipinfo", "book", "movie", "clock"}],
                         ids=lambda v: v if "." in str(v) else None)
async def test_answer_is_about_what_was_asked(feature, example, live_bot):
    """Relevance: the answer should mention (part of) the thing asked about."""
    reply = (await live_bot.respond("rel", example)).lower()
    wanted = [a.lower().split()[0].strip("*") for a in _args_of(example)]
    if wanted:
        assert any(w[:4] in reply for w in wanted), f"{example!r} -> reply never mentions {wanted}:\n{reply[:300]}"


async def test_follow_up_works_against_the_real_api(live_bot):
    first = await live_bot.respond("fu", "weather in Lahore")
    second = await live_bot.respond("fu", "what about Karachi")
    assert "Lahore" in first and "Karachi" in second
    assert (await live_bot.respond("fu", "forecast for Tokyo")).startswith("📅")


async def test_news_pick_a_number_returns_a_real_link(live_bot):
    assert "Top headlines" in await live_bot.respond("n", "today's news")
    link = await live_bot.respond("n", "1")
    assert link.startswith("🔗") and "https://" in link


async def test_link_preview_sections(live_bot):
    assert "Example Domain" in await live_bot.respond("l", "https://example.com")
    assert "Tech stack" in await live_bot.respond("l", "tech")
    assert "Security" in await live_bot.respond("l", "security")
