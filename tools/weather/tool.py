"""Weather: two features, `current` (now + 3 days) and `forecast` (5 days with rain chance). Open-Meteo, no API key."""
from datetime import datetime

from app.core.schemas import Followup, Input, UserError
from app.core.tool import Tool
from app.nlu.entities import DATE_WORDS, canonical, days_ahead, describe

from . import service
from .schemas import Day

tool = Tool("weather", category="everyday", title="Weather", emoji="🌦️", description="Weather & forecasts", synonyms={"climate": "weather", "prognosis": "forecast"})

WMO = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"), 48: ("Rime fog", "🌫️"), 51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"),
    55: ("Heavy drizzle", "🌧️"), 61: ("Light rain", "🌧️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    71: ("Light snow", "🌨️"), 73: ("Snow", "❄️"), 75: ("Heavy snow", "❄️"), 77: ("Snow grains", "❄️"),
    80: ("Rain showers", "🌦️"), 81: ("Rain showers", "🌧️"), 82: ("Violent showers", "⛈️"),
    85: ("Snow showers", "🌨️"), 86: ("Heavy snow showers", "🌨️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm + hail", "⛈️"), 99: ("Severe thunderstorm", "⛈️"),
}
# `when` is filled by the entity pre-pass ("weather next monday in karachi") or by a follow-up ("and tomorrow")
INPUTS = {"place": Input(required=True), "when": Input(pattern=DATE_WORDS)}
FOLLOWUPS = [Followup(phrases=["and {when}", "what about {when}", "how about {when}", "{when}"], overrides=["when"]),
             Followup(phrases=["what about {place}", "how about {place}", "and {place}"], overrides=["place"])]
MAX_DAYS_AHEAD = 15


def wmo(code: int) -> tuple[str, str]:
    return WMO.get(code, ("Unknown", "🌡️"))


def _range(day: Day) -> str:
    return f"{day.temperature_2m_min:.0f}–{day.temperature_2m_max:.0f}°C"


@tool.feature(
    "current", repeat="reuse", description="Current weather + 3-day outlook",
    phrases=["weather in {place}", "weather {place}", "the weather in {place}", "what's the weather in {place}",
             "how is the weather in {place}", "temperature in {place}", "what is the temperature in {place}", "what's the temperature in {place}", "how is the temperature in {place}",
             "what is the temperature like in {place}", "is it raining in {place}",
             "is it hot in {place}", "is it cold in {place}", "tell me the weather in {place}", "what is the weather in {place}",
             "how is the weather in {place}", "how's the weather in {place}", "what's the weather like in {place}", "weather like in {place}",
             "how hot is it in {place}", "how cold is it in {place}", "what's the weather", "what is the weather", "weather today",
             "weather now", "the weather", "tell me the weather", "{place} ka mausam", "{place} ka mausam kaisa hai",
             "{place} mein mausam", "mausam {place}", "ka mausam {place}", "aaj ka mausam {place}", "aaj ka mausam", "mausam"],
    keywords=["weather", "temperature"],
    examples=["weather in lahore", "is it raining in karachi"],
    negatives=["next week", "tomorrow", "forecast", "whether or not"],
    inputs=INPUTS, followups=FOLLOWUPS)
async def current(ctx, place, when):
    if canonical(when) == "next week":
        return await _week(ctx, place)
    if days_ahead(when) not in (None, 0):                       # "weather tomorrow in karachi" is a question about another day
        return await _day(ctx, place, when)
    r = await service.fetch(ctx.services.http, place, 3)
    c = r.data.current
    desc, icon = wmo(c.weather_code)
    lines = [f"{icon} {r.title}",
             f"{desc} · 🌡️ {c.temperature_2m:.0f}°C (feels {c.apparent_temperature:.0f}°C)",
             f"💧 {c.relative_humidity_2m}% · 💨 {c.wind_speed_10m:.0f} km/h", ""]
    for day in r.data.daily.days:
        when = datetime.fromisoformat(day.time).strftime("%a")
        lines.append(f"{wmo(day.weather_code)[1]} {when}: {_range(day)}")
    return "\n".join(lines)


@tool.feature(
    "forecast", repeat="reuse", description="5-day forecast with rain chance",
    phrases=["forecast for {place}", "forecast in {place}", "forecast {place}", "{place} forecast",
             "weather forecast for {place}", "will it rain in {place}", "is it going to rain in {place}", "going to rain in {place}",
             "do i need an umbrella in {place}", "will i need an umbrella in {place}"],   # dates ("tomorrow", "next monday") are lifted out first
    keywords=["forecast"],
    examples=["forecast for tokyo", "forecast next week in dubai"],
    negatives=["weather in"],
    inputs=INPUTS, followups=FOLLOWUPS)
async def forecast(ctx, place, when):
    if canonical(when) == "next week":
        return await _week(ctx, place)
    if days_ahead(when) not in (None, 0):
        return await _day(ctx, place, when)
    r = await service.fetch(ctx.services.http, place, 5)
    lines = [f"📅 5-day forecast — {r.title}", ""]
    for day in r.data.daily.days:
        desc, icon = wmo(day.weather_code)
        when = datetime.fromisoformat(day.time).strftime("%a %d")
        lines.append(f"{icon} *{when}* {_range(day)} · {desc} · ☔ {day.precipitation_probability_max or 0}%")
    return "\n".join(lines)


async def _day(ctx, place: str, when: str) -> str:
    """One day in detail ('tomorrow', 'next monday', 'in 3 days') followed by the days after it."""
    offset = days_ahead(when)
    if offset > MAX_DAYS_AHEAD:
        raise UserError(f"📅 I can look up to {MAX_DAYS_AHEAD} days ahead. Try a nearer date.")
    r = await service.fetch(ctx.services.http, place, min(offset + 4, 16))
    days = r.data.daily.days
    if offset >= len(days):
        raise UserError(f"📅 I only have a forecast for the next {len(days)} days here. Try a nearer date.")
    d = days[offset]
    desc, icon = wmo(d.weather_code)
    rain = f" · ☔ {d.precipitation_probability_max}% chance of rain" if d.precipitation_probability_max is not None else ""
    lines = [f"📅 *{datetime.fromisoformat(d.time):%A %d %b}* ({describe(when)}) — {r.title}", f"{icon} {desc} · 🌡️ {_range(d)}{rain}"]
    after = days[offset + 1: offset + 4]
    if after:
        lines += ["", "Then:"] + [f"{wmo(x.weather_code)[1]} {datetime.fromisoformat(x.time):%a %d}: {_range(x)}" for x in after]
    return "\n".join(lines)


async def _week(ctx, place: str) -> str:
    r = await service.fetch(ctx.services.http, place, 7)
    lines = [f"📅 7-day forecast — {r.title}", ""]
    for day in r.data.daily.days:
        desc, icon = wmo(day.weather_code)
        lines.append(f"{icon} *{datetime.fromisoformat(day.time):%a %d}* {_range(day)} · {desc} · ☔ {day.precipitation_probability_max or 0}%")
    return "\n".join(lines)
