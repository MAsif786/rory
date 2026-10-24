import pytest

from app.core.context import SESSION_TTL, TURN_TTL, ContextStore
from app.core.dispatcher import Dispatcher
from app.core.registry import Registry
from app.intent.rule_based import decide
from app.smart import Bot
from tests import fake_tools as ft


class Clock:
    t = 0.0
    def __call__(self): return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def bot(make_tools, clock):
    root, pkg = make_tools({"weather": ft.WEATHER, "countdown": ft.COUNTDOWN})
    reg = Registry().discover(root, pkg)
    return Bot(reg, Dispatcher(reg), decide, ContextStore(clock))


async def say(bot, text):
    return await bot.handle("chat", text)


async def test_new_tool_works_with_no_engine_edits(bot):
    assert await say(bot, "weather in lahore") == "lahore today"
    assert await say(bot, "is it raining in karachi?") == "karachi today"


async def test_no_false_positives(bot):
    for text in ["whether or not to go", "good morning", "i like rain"]:
        assert await say(bot, text) is None


async def test_keyword_only_asks_then_uses_answer(bot):
    assert await say(bot, "what's the weather") == "Which place?"
    assert await say(bot, "multan") == "multan today"


async def test_followup_changes_one_arg_keeps_rest(bot):
    await say(bot, "weather in lahore")
    assert await say(bot, "and tomorrow") == "lahore tomorrow"
    assert await say(bot, "what about karachi") == "karachi tomorrow"


async def test_fresh_match_beats_followup(bot):
    await say(bot, "weather in lahore")
    assert await say(bot, "weather in paris") == "paris today"


async def test_expired_context_ignored(bot, clock):
    await say(bot, "weather in lahore")
    clock.t = TURN_TTL + 1
    assert await say(bot, "and tomorrow") is None


async def test_active_game_beats_commands_and_nlu(bot):
    assert await say(bot, "play countdown") == "3"
    assert await say(bot, "ping") == "2"                     # game wins over the direct command
    assert await say(bot, "weather in lahore") == "1"        # ...and over the intent engine
    assert await say(bot, "x") == "liftoff"                  # finished
    assert await say(bot, "ping") == "pong 🏓"


async def test_passthrough_falls_to_next_step(bot):
    await say(bot, "play countdown")
    assert "🏠 *Home*" in await say(bot, "hello")           # greeting + menu, not the game's reply
    assert await say(bot, "ping") == "2"                     # game still active


async def test_stop_always_ends_game(bot):
    await say(bot, "play countdown")
    assert await say(bot, "stop") == "Game ended."
    assert await say(bot, "ping") == "pong 🏓"


async def test_session_expires_after_idle(bot, clock):
    await say(bot, "play countdown")
    clock.t = SESSION_TTL + 1
    assert await say(bot, "ping") == "pong 🏓"


async def test_session_idle_timer_resets_on_activity(bot, clock):
    await say(bot, "play countdown")
    clock.t = SESSION_TTL - 1
    await say(bot, "go")
    clock.t = 2 * SESSION_TTL - 2
    assert await say(bot, "go") == "1"


async def test_help_lists_examples(bot):
    assert "weather in lahore" in await say(bot, "help")
