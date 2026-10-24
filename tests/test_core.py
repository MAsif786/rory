import pytest

from app.core.dispatcher import GENERIC_ERROR, Dispatcher
from app.core.registry import Registry
from app.core.schemas import Context
from tests import fake_tools as ft


def load(make_tools, **tools):
    root, pkg = make_tools(tools)
    return Registry().discover(root, pkg)


def test_discovers_tools_and_ignores_underscore_folders(make_tools):
    reg = load(make_tools, weather=ft.WEATHER, _draft="syntax error here")
    assert set(reg.tools) == {"weather"} and not reg.rejected
    assert [s.full_name for s in reg.specs()] == ["weather.current"]


@pytest.mark.parametrize("src, why", [
    ("from app.core.tool import Tool\ntool = Tool('other')\n", "must equal tool name"),
    ("from app.core.tool import Tool\ntool = Tool('bad')\n", "at least one"),
    ("raise ImportError('nope')", "nope"),
    ("x = 1", "define `tool"),
    ("from app.core.tool import Tool\ntool = Tool('bad')\n@tool.feature('a', phrases=['hi {x}'], examples=['hi'])\nasync def a(ctx): ...", "{x}"),
    ("from app.core.tool import Tool\ntool = Tool('bad')\n@tool.feature('a', phrases=['hi'])\nasync def a(ctx): ...", "example"),
    ("from app.core.tool import Tool\ntool = Tool('bad')\n@tool.feature('a', phrases=['hi'], examples=['hi'])\ndef a(ctx): ...", "async def"),
    ("from app.core.tool import Tool\ntool = Tool('bad')\n@tool.feature('a', phrases=['hi'], examples=['hi'], kind='session')\nasync def a(ctx): ...", "session"),
    ("from app.core.tool import Tool\nfrom app.core.schemas import Followup\ntool = Tool('bad')\n@tool.feature('a', phrases=['hi'], examples=['hi'], followups=[Followup(phrases=['x'], overrides=['q'])])\nasync def a(ctx): ...", "unknown input"),
])
def test_bad_tool_rejected_others_still_load(make_tools, src, why):
    reg = load(make_tools, bad=src, weather=ft.WEATHER)
    assert "bad" in reg.rejected and why in reg.rejected["bad"]
    assert "weather" in reg.tools


def test_duplicate_phrase_rejected(make_tools):
    dup = ft.WEATHER.replace('Tool("weather")', 'Tool("weather2")')
    reg = load(make_tools, weather=ft.WEATHER, weather2=dup)
    assert "weather" in reg.tools and "already claimed" in reg.rejected["weather2"]


def test_specs_hold_no_handlers(make_tools):
    spec = load(make_tools, weather=ft.WEATHER).specs()[0]
    assert not hasattr(spec, "handler")


async def run(reg, feature, args, timeout=5):
    return await Dispatcher(reg, timeout).run_feature(feature, args, Context("c", "", None))


async def test_dispatcher_validates_and_runs(make_tools):
    reg = load(make_tools, weather=ft.WEATHER)
    assert (await run(reg, "weather.current", {"place": "lahore"})).reply == "lahore today"
    assert not (await run(reg, "weather.current", {})).ok                       # missing required
    assert "Unknown" in (await run(reg, "weather.current", {"place": "x", "bogus": 1})).reply
    assert "one of" in (await run(reg, "weather.current", {"place": "x", "day": "never"})).reply


async def test_dispatcher_hides_errors_and_times_out(make_tools):
    reg = load(make_tools, boom=ft.BOOM)
    r = await run(reg, "boom.go", {})
    assert r.reply == GENERIC_ERROR and "secret" not in r.reply

    slow = '''
import asyncio
from app.core.tool import Tool
tool = Tool("slow")
@tool.feature("go", phrases=["wait"], examples=["wait"])
async def go(ctx):
    await asyncio.sleep(5)
'''
    assert (await run(load(make_tools, slow=slow), "slow.go", {}, timeout=0.05)).reply == GENERIC_ERROR


async def test_upstream_http_errors_get_a_network_message(make_tools):
    src = '''
import httpx
from app.core.tool import Tool
tool = Tool("flaky")
@tool.feature("go", phrases=["go"], examples=["go"])
async def go(ctx):
    raise httpx.ReadTimeout("slow")
'''
    from app.core.dispatcher import NETWORK_ERROR
    assert (await run(load(make_tools, flaky=src), "flaky.go", {})).reply == NETWORK_ERROR
