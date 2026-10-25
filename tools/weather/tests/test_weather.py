"""Weather tests: offline, with a fake HTTP client, plus routing through the real registry."""
from types import SimpleNamespace

import pytest

from app.core.context import ContextStore
from app.core.dispatcher import Dispatcher
from app.core.registry import Registry
from app.core.schemas import Context
from app.intent.rule_based import decide
from app.smart import Bot

PLACE = {"name": "Lahore", "country": "Pakistan", "latitude": 31.5, "longitude": 74.3}
DAYS = 5
API = {"current": {"weather_code": 1, "temperature_2m": 21.4, "apparent_temperature": 20.6, "relative_humidity_2m": 63, "wind_speed_10m": 3.2},
       "daily": {"time": [f"2026-10-{25 + i}" for i in range(DAYS)], "weather_code": [0, 61, 3, 95, 1],
                 "temperature_2m_min": [17] * DAYS, "temperature_2m_max": [29] * DAYS, "precipitation_probability_max": [0, 80, 10, None, 5]}}


class FakeHttp:
    def __init__(self, fail=False):
        self.fail, self.cities, self.days = fail, [], []

    async def get(self, url, params):
        if self.fail:
            raise RuntimeError("upstream down")
        if "geocoding" in url:
            self.cities.append(params["name"])
            body = {} if params["name"] == "nowhereville" else {"results": [PLACE]}
        else:
            self.days.append(params["forecast_days"])
            body = API
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)


def make_bot(http):
    from tools.weather.tool import tool
    reg = Registry()
    reg.add(tool, "weather")                         # only this tool, so other tools can't change these results
    assert "weather" in reg.tools, reg.rejected
    return Bot(reg, Dispatcher(reg), decide, ContextStore(), SimpleNamespace(http=http))


@pytest.fixture
def http():
    return FakeHttp()


@pytest.fixture
def bot(http):
    return make_bot(http)


async def test_current_formats_report(bot):
    out = await bot.handle("c", "weather in Lahore")
    assert "*Lahore, Pakistan*" in out and "21°C (feels 21°C)" in out and "💧 63%" in out
    assert len(out.splitlines()) == 4 + DAYS     # fake API returns 5 days regardless


async def test_forecast_shows_rain_chance_and_handles_missing(bot):
    out = await bot.handle("c", "forecast for Lahore")
    assert "5-day forecast" in out and "☔ 80%" in out and "☔ 0%" in out


@pytest.mark.parametrize("text, title", [
    ("is it raining in Karachi", "Lahore"), ("weather next week in Dubai", "7-day"), ("will it rain tomorrow in Murree", "(tomorrow)"),
    ("what's the weather in Paris?", "Lahore"), ("Dubai forecast", "5-day")])
async def test_routing(bot, text, title):
    assert title in await bot.handle("c", text)


async def test_missing_city_asks_then_answers(bot):
    assert await bot.handle("c", "what's the weather") == "Which place?"
    assert "Lahore" in await bot.handle("c", "Lahore")


async def test_followup_switches_place(bot, http):
    await bot.handle("c", "forecast for Lahore")
    out = await bot.handle("c", "what about Karachi")
    assert "5-day" in out and http.cities == ["Lahore", "Karachi"]


async def test_unknown_place_is_friendly(bot):
    assert "Couldn't find a place called *nowhereville*" in await bot.handle("c", "weather in nowhereville")


async def test_upstream_failure_is_generic():
    out = await make_bot(FakeHttp(fail=True)).handle("c", "weather in lahore")
    assert "Something went wrong" in out and "upstream" not in out


async def test_no_false_positives(bot):
    for text in ["whether or not to go", "good morning", "tell me a joke"]:
        assert await bot.handle("c", text) is None


async def test_api_shape_change_fails_safely(bot, monkeypatch):
    monkeypatch.setitem(API, "current", {"weather_code": "oops"})
    out = await bot.handle("c", "weather in lahore")
    assert "Something went wrong" in out


# --- dates: lifted out of the message by the entity pre-pass, answered for that day --------------------------------------------
async def test_tomorrow_shows_that_day_in_detail(bot, http):
    out = await bot.handle("c", "weather tomorrow in Karachi")
    assert out.startswith("📅 *Monday 26 Oct* (tomorrow) — *Lahore, Pakistan*") and "Light rain" in out and "☔ 80% chance of rain" in out
    assert http.cities == ["Karachi"] and "Then:" in out                     # "tomorrow in" never leaks into the place


async def test_a_weekday_asks_the_api_for_enough_days(bot, http):
    await bot.handle("c", "forecast for the weekend in Dubai")
    await bot.handle("c", "weather in 3 days in Paris")
    assert http.cities == ["Dubai", "Paris"] and all(d >= 4 for d in http.days)


async def test_weather_tomorrow_without_a_place_asks_and_remembers_the_day(bot, http):
    assert await bot.handle("c", "weather tomorrow") == "Which place?"
    out = await bot.handle("c", "Multan")
    assert "(tomorrow)" in out and http.cities == ["Multan"]


async def test_and_tomorrow_followup_changes_only_the_day(bot, http):
    await bot.handle("c", "weather in Lahore")
    out = await bot.handle("c", "and tomorrow")
    assert "(tomorrow)" in out and http.cities == ["Lahore", "Lahore"]
    out = await bot.handle("c", "what about Karachi")                          # the place changes, the day is kept
    assert "(tomorrow)" in out and http.cities[-1] == "Karachi"


async def test_too_far_ahead_is_a_friendly_error(bot):
    assert "up to 15 days ahead" in await bot.handle("c", "weather in 30 days in Paris")


async def test_roman_urdu_tomorrow(bot, http):
    assert "(tomorrow)" in await bot.handle("c", "kal ka mausam lahore")
    assert http.cities == ["lahore"]
