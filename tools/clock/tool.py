"""Local time in any city or timezone."""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.schemas import Followup, Input
from app.core.tool import Tool
from app.geo import geocode

tool = Tool("clock", category="everyday", title="Clock", emoji="🕐", description="Time in any city")

PLACE = r"[^\d]{2,40}"
NOT_PLACES = ["bed time", "story time", "game time", "prime time", "free time", "real time", "part time", "full time", "long time",
              "any time", "same time", "next time", "last time", "first time", "this time", "that time", "good time", "big time",
              "quality time", "spare time", "time to", "time for", "time of", "time zone", "one more time", "once more time", "another time", "every time",
              "each time", "all the time", "about time", "on time", "in time", "high time", "lunch time", "dinner time", "play time", "show time",
              "one time", "two time", "three time", "some time", "no time", "more time", "less time", "extra time", "half time", "full time"]


@tool.feature(
    "time", description="Local time in a city or timezone",
    phrases=["time in {place}", "what time is it in {place}", "what's the time in {place}", "whats the time in {place}",
             "what is the time in {place}", "current time in {place}", "local time in {place}", "time now in {place}",
             "{place} time", "time {place}", "what time is it", "what's the time", "time now", "current time", "time"],
    examples=["time in Tokyo", "what time is it in London"],
    negatives=NOT_PLACES,
    inputs={"place": Input(default="UTC", pattern=PLACE)},
    followups=[Followup(phrases=["what about {place}", "and in {place}", "how about {place}"], overrides=["place"])])
async def time_(ctx, place):
    label, zone = place, None
    if "/" in place or place.upper() == "UTC":
        try:
            zone = ZoneInfo(place if "/" in place else "UTC")
        except (ZoneInfoNotFoundError, ValueError):
            zone = None
    if zone is None:
        found = await geocode(ctx.services.http, place)
        label, zone = f"{found.name}, {found.country}", ZoneInfo(found.timezone)
    now = datetime.now(zone)
    return f"🕐 *{label}*\n{now:%A, %d %b %Y}\n⏰ *{now:%I:%M %p}* ({now:%Z}, UTC{now:%z})"
