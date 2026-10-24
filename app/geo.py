"""Geocoding via Open-Meteo (no key), shared by tools that need a place (weather, clock)."""
from pydantic import BaseModel

from app.core.schemas import UserError

GEO = "https://geocoding-api.open-meteo.com/v1/search"


class Place(BaseModel):
    name: str
    country: str = ""
    latitude: float
    longitude: float
    timezone: str = "UTC"


class _Response(BaseModel):
    results: list[Place] = []


async def geocode(http, name: str) -> Place:
    """`http` is ctx.services.http. Raises UserError for an unknown place; network errors propagate."""
    r = await http.get(GEO, params={"name": name, "count": 1, "language": "en"})
    r.raise_for_status()
    found = _Response.model_validate(r.json()).results
    if not found:
        raise UserError(f"📍 Couldn't find a place called *{name}*.")
    return found[0]
