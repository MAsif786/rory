"""Weather: two features, `current` (now + 3 days) and `forecast` (5 days with rain chance). Open-Meteo, no API key."""
from datetime import datetime

from app.core.schemas import Followup, Input
from app.core.tool import Tool

from . import service
from .schemas import Day

tool = Tool("weather", title="Weather", emoji="🌦️", description="Current weather and forecasts")

WMO = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"), 48: ("Rime fog", "🌫️"), 51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"),
    55: ("Heavy drizzle", "🌧️"), 61: ("Light rain", "🌧️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    71: ("Light snow", "🌨️"), 73: ("Snow", "❄️"), 75: ("Heavy snow", "❄️"), 77: ("Snow grains", "❄️"),
    80: ("Rain showers", "🌦️"), 81: ("Rain showers", "🌧️"), 82: ("Violent showers", "⛈️"),
    85: ("Snow showers", "🌨️"), 86: ("Heavy snow showers", "🌨️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm + hail", "⛈️"), 99: ("Severe thunderstorm", "⛈️"),
}
PLACE = {"place": Input(required=True)}
SWITCH_PLACE = [Followup(phrases=["what about {place}", "how about {place}", "and {place}"], overrides=["place"])]


def wmo(code: int) -> tuple[str, str]:
    return WMO.get(code, ("Unknown", "🌡️"))


def _range(day: Day) -> str:
    return f"{day.temperature_2m_min:.0f}–{day.temperature_2m_max:.0f}°C"


@tool.feature(
    "current", description="Current weather + 3-day outlook",
    phrases=["weather in {place}", "weather {place}", "the weather in {place}", "what's the weather in {place}",
             "how is the weather in {place}", "temperature in {place}", "is it raining in {place}",
             "is it hot in {place}", "is it cold in {place}"],
    keywords=["weather", "temperature"],
    examples=["weather in lahore", "is it raining in karachi"],
    negatives=["next week", "tomorrow", "forecast", "whether or not"],
    inputs=PLACE, followups=SWITCH_PLACE)
async def current(ctx, place):
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
    "forecast", description="5-day forecast with rain chance",
    phrases=["forecast for {place}", "forecast in {place}", "forecast {place}", "{place} forecast",
             "weather forecast for {place}", "weather next week in {place}", "weather tomorrow in {place}",
             "will it rain in {place}", "will it rain tomorrow in {place}"],
    keywords=["forecast"],
    examples=["forecast for tokyo", "weather next week in dubai"],
    negatives=["weather in"],
    inputs=PLACE, followups=SWITCH_PLACE)
async def forecast(ctx, place):
    r = await service.fetch(ctx.services.http, place, 5)
    lines = [f"📅 5-day forecast — {r.title}", ""]
    for day in r.data.daily.days:
        desc, icon = wmo(day.weather_code)
        when = datetime.fromisoformat(day.time).strftime("%a %d")
        lines.append(f"{icon} *{when}* {_range(day)} · {desc} · ☔ {day.precipitation_probability_max or 0}%")
    return "\n".join(lines)
