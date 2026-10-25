import pytest

from app import replies
from app.core.context import ContextStore
from app.core.dispatcher import Dispatcher
from app.core.registry import Registry
from app.intent.rule_based import decide
from app.smart import Bot
from tests import fake_tools as ft

WEATHER = ft.WEATHER.replace('Tool("weather")', 'Tool("weather", title="Weather", emoji="🌦️", description="Weather and forecasts")')


@pytest.fixture
def bot(make_tools):
    root, pkg = make_tools({"weather": WEATHER, "countdown": ft.COUNTDOWN})
    reg = Registry().discover(root, pkg)
    return Bot(reg, Dispatcher(reg), decide, ContextStore())


async def say(bot, text):
    return await bot.handle("c", text)


@pytest.mark.parametrize("word", ["menu", "home", "start", "help", "!help", "/menu", "Menu"])
async def test_menu_aliases_show_home(bot, word):
    out = await say(bot, word)
    assert out.startswith("🏠 *Home*") and "🧩 *More* — Weather and forecasts" in out                      # a tool with no category is listed under More, never hidden
    assert "_weather in lahore_" in out and "🎮 *Games* — Countdown" in out                  # session tools are the Games group, with default metadata


async def test_help_tool_feature_and_all(bot):
    assert "• *weather.current*" in await say(bot, "help weather")
    page = await say(bot, "help weather.current")
    assert "Needs: place, day (optional)" in page and "part of the *weather* tool" in page
    assert "weather.current" in await say(bot, "help current")             # unique short feature name
    allp = await say(bot, "help all")
    assert "Weather" in allp and "current" in allp and "Countdown" in allp and "start" in allp


async def test_help_unknown(bot):
    assert "No group, tool or feature called *nope*" in await say(bot, "help nope")


async def test_hi_is_a_greeting_not_the_menu(make_tools):
    from tools.greetings.tool import tool as greetings
    root, pkg = make_tools({})
    reg = Registry().discover(root, pkg)
    reg.add(greetings, "greetings")
    out = await Bot(reg, Dispatcher(reg), decide, ContextStore()).handle("c", "hi")
    assert "I'm Rory" in out and "Home" not in out


async def test_menu_and_help_work_mid_game_without_ending_it(bot):
    await say(bot, "play countdown")
    assert "🏠 *Home*" in await say(bot, "menu")
    assert "Countdown" in await say(bot, "help all")
    assert await say(bot, "x") == "2"                                       # game is still on


async def test_empty_registry(make_tools):
    root, pkg = make_tools({})
    reg = Registry().discover(root, pkg)
    bot = Bot(reg, Dispatcher(reg), decide, ContextStore())
    assert "No tools are installed" in await say(bot, "help")


async def test_fallback_uses_installed_examples(bot):
    out = replies.not_understood(bot.registry)
    assert out.startswith("🤔 I didn't get that.") and "_weather in lahore_" in out and "*menu*" in out


# --- unknown words -------------------------------------------------------------------------------------------------
@pytest.fixture
def fb_bot(make_tools):
    from tools.wiki.tool import tool as wiki
    root, pkg = make_tools({"weather": WEATHER})
    reg = Registry().discover(root, pkg)
    reg.add(wiki, "wiki")
    return Bot(reg, Dispatcher(reg), decide, ContextStore())


async def respond(bot, text):
    return await bot.respond("c", text)


@pytest.mark.parametrize("text", ["super", "Nice!", "ok", "lol", "👍", "mashallah"])
async def test_small_talk_is_acknowledged_not_rejected(fb_bot, text):
    out = await respond(fb_bot, text)
    assert "didn't get that" not in out and "help" in out


async def test_small_typo_is_repaired_and_answered(fb_bot):
    assert await respond(fb_bot, "wether in lahore") == "lahore today"


async def test_bigger_typo_gets_a_did_you_mean(fb_bot):
    assert "Did you mean _weather in lahore_?" in await respond(fb_bot, "wtr in lahore")


async def test_short_unknown_word_offers_a_wikipedia_lookup(fb_bot):
    out = await respond(fb_bot, "zorblax")
    assert "I don't know *zorblax*" in out and "tell me about zorblax" in out


async def test_long_unknown_sentence_shows_real_examples(fb_bot):
    out = await respond(fb_bot, "the quick brown fox jumps over the lazy dog today")
    assert out.startswith("🤔 I didn't get that.") and "_weather in lahore_" in out


async def test_asking_the_unknown_again_changes_the_reply(fb_bot):
    first, second = await respond(fb_bot, "zorblax"), await respond(fb_bot, "zorblax")
    assert "I don't know" in first and second.startswith("🤔 Still not sure")
