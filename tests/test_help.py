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
    assert out.startswith("🏠 *Home*") and "🌦️ *Weather* — Weather and forecasts" in out
    assert "_weather in lahore_" in out and "🎮 *Games*" in out and "🧩 Countdown" in out   # session tools are listed under Games, with default metadata


async def test_help_tool_feature_and_all(bot):
    assert "• *weather.current*" in await say(bot, "help weather")
    page = await say(bot, "help weather.current")
    assert "Needs: place, day (optional)" in page and "part of the *weather* tool" in page
    assert "weather.current" in await say(bot, "help current")             # unique short feature name
    allp = await say(bot, "help all")
    assert "weather.current" in allp and "countdown.start" in allp


async def test_help_unknown(bot):
    assert "No tool or feature called *nope*" in await say(bot, "help nope")


async def test_hi_greets_with_menu(bot):
    out = await say(bot, "hi")
    assert out.startswith(tuple(replies.GREETING)) and "🏠 *Home*" in out


async def test_menu_and_help_work_mid_game_without_ending_it(bot):
    await say(bot, "play countdown")
    assert "🏠 *Home*" in await say(bot, "menu")
    assert "countdown.start" in await say(bot, "help all")
    assert await say(bot, "x") == "2"                                       # game is still on


async def test_empty_registry(make_tools):
    root, pkg = make_tools({})
    reg = Registry().discover(root, pkg)
    bot = Bot(reg, Dispatcher(reg), decide, ContextStore())
    assert "No tools are installed" in await say(bot, "help")


async def test_fallback_uses_installed_examples(bot):
    out = replies.not_understood(bot.registry)
    assert out.startswith("🤔 I didn't get that.") and "_weather in lahore_" in out and "*menu*" in out
