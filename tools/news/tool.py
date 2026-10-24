"""News headlines from Google News (RSS, no key): today's top stories, or news about a topic."""
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from app.core.schemas import Followup, Input, UserError
from app.core.tool import Tool

tool = Tool("news", title="News", emoji="📰", description="Today's headlines, or news about any topic")

MAX_ITEMS = 5
MAX_BYTES = 1_000_000
TOPIC = r"(?!(?:i|me|my|you|your|we|us|our|top|latest|today|today's|todays|breaking|the|any|what's|whats)\b)[^\n]{2,60}"
NOT_NEWS = ["good news", "bad news", "no news", "fake news", "some news", "big news", "news to me", "great news", "sad news"]


def _edition() -> tuple[str, str]:
    """Google News region from NEWS_COUNTRY (two letters, default US) -> (gl, ceid)."""
    gl = (os.getenv("NEWS_COUNTRY", "US").strip().upper() or "US")[:2]
    return gl, f"{gl}:en"


def _ago(pub: str) -> str:
    try:
        secs = (datetime.now(timezone.utc) - parsedate_to_datetime(pub)).total_seconds()
    except (TypeError, ValueError):
        return ""
    return f"{max(int(secs // 60), 1)}m ago" if secs < 3600 else f"{int(secs // 3600)}h ago" if secs < 86400 else f"{int(secs // 86400)}d ago"


async def fetch(http, topic: str | None) -> list[dict]:
    gl, ceid = _edition()
    base = "https://news.google.com/rss"
    params = {"hl": "en", "gl": gl, "ceid": ceid}
    if topic:
        base, params["q"] = f"{base}/search", f"{topic} when:2d"      # recent stories only
    r = await http.get(base, params=params)
    r.raise_for_status()
    if len(r.text) > MAX_BYTES:
        raise UserError("📰 The news feed was too large to read. Please try again.")
    try:
        items = ET.fromstring(r.text).findall("./channel/item")
    except ET.ParseError:
        raise UserError("📰 I couldn't read the news feed right now. Please try again in a moment.") from None
    out = []
    for it in items[:MAX_ITEMS]:
        title, source = (it.findtext("title") or "").rsplit(" - ", 1) if " - " in (it.findtext("title") or "") else (it.findtext("title") or "", "")
        out.append({"title": title.strip(), "source": source.strip() or (it.findtext("source") or ""), "link": it.findtext("link") or "",
                    "ago": _ago(it.findtext("pubDate") or "")})
    return out


def format_items(heading: str, items: list[dict]) -> str:
    lines = [heading, ""]
    for i, n in enumerate(items, 1):
        meta = " · ".join(x for x in (n["source"], n["ago"]) if x)
        lines.append(f"{i}. *{n['title']}*" + (f"\n   _{meta}_" if meta else "") + f"\n   {n['link']}")
    return "\n".join(lines)


@tool.feature(
    "headlines", description="Today's top headlines", repeat="reuse",
    phrases=["news", "the news", "today's news", "todays news", "today news", "news today", "latest news", "the latest news", "top news",
             "top stories", "headlines", "top headlines", "today's headlines", "todays headlines", "headlines today", "what's the news",
             "whats the news", "what's in the news", "any news", "breaking news", "news update", "give me the news", "show me the news"],
    examples=["today's news", "top headlines"],
    negatives=NOT_NEWS)
async def headlines(ctx):
    items = await fetch(ctx.services.http, None)
    if not items:
        raise UserError("📰 No headlines right now. Please try again later.")
    return format_items("📰 *Top headlines*", items)


@tool.feature(
    "about", description="Recent news about a topic (news about Mars, Pakistan news)", repeat="reuse",
    phrases=["news about {topic}", "news on {topic}", "news for {topic}", "news from {topic}", "news in {topic}", "latest news about {topic}",
             "latest news on {topic}", "latest {topic} news", "today's news about {topic}", "{topic} news", "{topic} headlines",
             "{topic} news today", "what's the news on {topic}", "any news about {topic}", "search news for {topic}", "news {topic}"],
    keywords=["news", "headlines"],
    examples=["news about mars", "pakistan news"],
    negatives=NOT_NEWS,
    inputs={"topic": Input(required=True, pattern=TOPIC, ask="📰 News about what? (e.g. *news about cricket*)")},
    followups=[Followup(phrases=["what about {topic}", "how about {topic}", "and {topic}"], overrides=["topic"])])
async def about(ctx, topic):
    items = await fetch(ctx.services.http, topic)
    if not items:
        raise UserError(f"📰 No recent news found about *{topic}*.")
    return format_items(f"📰 *News: {topic}*", items)
