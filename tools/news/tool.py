"""News headlines from Google News (RSS, no key): today's top stories, or news about a topic."""
import html
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from app.core.schemas import AGAIN, Followup, Input, UserError
from app.core.tool import Tool
from app.format import num, tip

tool = Tool("news", category="everyday", title="News", emoji="📰", description="Headlines & topic news", synonyms={"tidings": "news", "headline": "headlines"})

MAX_ITEMS = 5
MAX_BYTES = 1_000_000
TOPIC = (r"(?!(?:i|me|my|you|your|we|us|our|top|latest|today|today's|todays|breaking|the|any|what's|whats|tell|show|give|get)\b)"
         r"[^\n]{2,60}(?<!\ba)(?<!\ban)(?<!\bthe)(?<!\bis)(?<!\bwas)(?<!\bare)(?<!\bwere)(?<!\bto)(?<!\bof)(?<!\band)(?<!\bor)")
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


_RELATED = re.compile(r'<li><a href="[^"]*"[^>]*>(.*?)</a>(?:&nbsp;|\s)*(?:<font[^>]*>(.*?)</font>)?</li>', re.S)


def _related(description: str, title: str) -> list[tuple[str, str]]:
    """[(headline, outlet)] of other outlets' coverage of the same story, from the feed's description HTML."""
    out = []
    for head, outlet in _RELATED.findall(description or ""):
        head, outlet = html.unescape(re.sub(r"<[^>]+>", "", head)).strip(), html.unescape(outlet or "").strip()
        if head and head.lower() != title.lower() and outlet:
            out.append((head, outlet))
    return out


def _short(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


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
        related = _related(it.findtext("description") or "", title.strip())
        out.append({"title": title.strip(), "source": source.strip() or (it.findtext("source") or ""), "link": it.findtext("link") or "",
                    "ago": _ago(it.findtext("pubDate") or ""), "related": related})
    return out


_shown: dict[str, tuple[float, list[dict]]] = {}      # chat -> (when, the stories last listed), so "2" can open story 2
SHOWN_TTL = 15 * 60


def _remember(chat_id: str, items: list[dict], now: float) -> None:
    if len(_shown) > 500:
        _shown.clear()
    _shown[chat_id] = (now, items)


def _describe(n: dict) -> list[str]:
    """A short description under the headline: what another outlet reported, and who else covered the story."""
    lines = []
    if n["related"]:
        head, outlet = n["related"][0]
        lines.append(f"     ↳ {_short(head, 100)} ({outlet})")
        others = list(dict.fromkeys(o for _, o in n["related"][1:] if o != n["source"] and o != outlet))
        if others:
            lines.append("     _Also: " + ", ".join(others[:2]) + (f" +{len(others) - 2} more" if len(others) > 2 else "") + "_")
    return lines


def format_items(heading: str, subtitle: str, items: list[dict]) -> str:
    """Dated title, a one-line description, then numbered headlines with a short description each.
    The (very long) Google News links are sent on request, not listed."""
    lines = [f"{heading} — {datetime.now():%a %d %b}", f"_{subtitle}_", ""]
    for i, n in enumerate(items, 1):
        meta = " · ".join(x for x in (n["source"], n["ago"]) if x)
        lines += [f"{num(i)} *{n['title']}*", *([f"     _{meta}_"] if meta else []), *_describe(n), ""]
    return "\n".join([*lines, tip(f"Reply *1*–*{len(items)}* to get a link")])


def format_link(n: dict) -> str:
    meta = " · ".join(x for x in (n["source"], n["ago"]) if x)
    return f"🔗 *{n['title']}*\n" + (f"_{meta}_\n" if meta else "") + n["link"]


async def _show(ctx, topic: str | None, pick: int | None) -> str:
    cached = _shown.get(ctx.chat_id)
    if pick and cached and ctx.now - cached[0] < SHOWN_TTL:
        items = cached[1]                               # "2" right after a list opens the story that was listed
    else:
        items = await fetch(ctx.services.http, topic)
        if not items:
            raise UserError(f"📰 No recent news found about *{topic}*." if topic else "📰 No headlines right now. Please try again later.")
        _remember(ctx.chat_id, items, ctx.now)
    if pick:
        if pick > len(items):
            raise UserError(f"📰 Pick a number from 1 to {len(items)}.")
        return format_link(items[pick - 1])
    if topic:
        return format_items(f"📰 *News: {topic}*", f"Latest {len(items)} stories about {topic} (last 2 days), newest first", items)
    return format_items("📰 *Top headlines*", f"Top {len(items)} stories from Google News", items)


PICK = Input(type="int", pattern="[1-9]")
OPEN_STORY = Followup(phrases=["{pick}", "open {pick}", "link {pick}", "link for {pick}", "read {pick}", "story {pick}", "number {pick}",
                               "link to {pick}", "send {pick}"], overrides=["pick"])


@tool.feature(
    "headlines", description="Today's top headlines (reply 1-5 for a link)", repeat="reuse",
    phrases=["news", "the news", "today's news", "todays news", "today news", "news today", "latest news", "the latest news", "top news",
             "top stories", "headlines", "top headlines", "today's headlines", "todays headlines", "headlines today", "what's the news",
             "whats the news", "what's in the news", "any news", "any news today", "is there any news", "is there any news today", "got any news", "breaking news", "news update", "give me the news", "show me the news", "tell me the news", "tell me the latest news", "show me the latest news",
             "show me today's news", "tell me today's news", "what's happening in the world", "what is happening in the world",
             "what's happening today", "what's going on in the world", "what's going on today", "world news", "what are the headlines", "what are today's headlines",
             "khabrein", "khabar", "aaj ki khabrein", "taza khabrein", "mujhe khabrein batao", "khabrein batao"],
    examples=["today's news", "top headlines"],
    negatives=NOT_NEWS,
    inputs={"pick": PICK}, followups=[OPEN_STORY, Followup(phrases=AGAIN.phrases, sets={"pick": None})])
async def headlines(ctx, pick):
    return await _show(ctx, None, pick)


@tool.feature(
    "about", description="Recent news on a topic", repeat="reuse",
    phrases=["news about {topic}", "news on {topic}", "news for {topic}", "news from {topic}", "news in {topic}", "latest news about {topic}",
             "latest news on {topic}", "latest {topic} news", "today's news about {topic}", "{topic} news", "{topic} headlines",
             "{topic} news today", "what's the news on {topic}", "any news about {topic}", "search news for {topic}", "news {topic}"],
    keywords=["news", "headlines"],
    examples=["news about mars", "pakistan news"],
    negatives=NOT_NEWS,
    inputs={"topic": Input(required=True, pattern=TOPIC, ask="📰 News about what? (e.g. *news about cricket*)"), "pick": PICK},
    followups=[Followup(phrases=["what about {topic}", "how about {topic}", "and {topic}"], overrides=["topic"], sets={"pick": None}),
               OPEN_STORY, Followup(phrases=AGAIN.phrases, sets={"pick": None})])
async def about(ctx, topic, pick):
    return await _show(ctx, topic, pick)
