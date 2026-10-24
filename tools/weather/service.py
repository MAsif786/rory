"""Open-Meteo access: geocode a city and fetch its forecast. No formatting here."""
from dataclasses import dataclass

from app.core.schemas import UserError

GEO = "https://geocoding-api.open-meteo.com/v1/search"
API = "https://api.open-meteo.com/v1/forecast"


@dataclass
class Report:
    data: dict
    title: str              # "*Lahore, Pakistan*"


async def _get_json(http, url: str, **params) -> dict:
    r = await http.get(url, params=params)
    r.raise_for_status()
    return r.json()


async def fetch(http, city: str, days: int) -> Report:
    """`http` is ctx.services.http. Raises UserError for an unknown place; network errors propagate to the dispatcher."""
    found = await _get_json(http, GEO, name=city, count=1, language="en")
    if not found.get("results"):
        raise UserError(f"📍 Couldn't find a place called *{city}*.")
    place = found["results"][0]
    data = await _get_json(
        http, API, latitude=place["latitude"], longitude=place["longitude"], timezone="auto", forecast_days=days,
        temperature_unit="celsius", wind_speed_unit="kmh",
        current="temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
        daily="weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max")
    return Report(data, f"*{place['name']}, {place.get('country', '')}*")
