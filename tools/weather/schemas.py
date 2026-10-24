"""Open-Meteo response shapes. Validating here means an API change fails loudly in one place, not deep in formatting."""
from pydantic import BaseModel


class Place(BaseModel):
    name: str
    country: str = ""
    latitude: float
    longitude: float


class GeoResponse(BaseModel):
    results: list[Place] = []


class Current(BaseModel):
    weather_code: int
    temperature_2m: float
    apparent_temperature: float
    relative_humidity_2m: int
    wind_speed_10m: float


class Day(BaseModel):
    time: str
    weather_code: int
    temperature_2m_min: float
    temperature_2m_max: float
    precipitation_probability_max: int | None = None


class Daily(BaseModel):
    """Open-Meteo returns one list per field (columns); `days` turns them into one `Day` per date."""
    time: list[str]
    weather_code: list[int]
    temperature_2m_min: list[float]
    temperature_2m_max: list[float]
    precipitation_probability_max: list[int | None]

    @property
    def days(self) -> list[Day]:
        return [Day(**dict(zip(type(self).model_fields, row))) for row in zip(*(getattr(self, f) for f in type(self).model_fields))]


class Forecast(BaseModel):
    current: Current
    daily: Daily
