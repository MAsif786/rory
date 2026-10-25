"""Link previews: paste a URL for a summary, then ask for its links, contacts, tech, security or text."""
import json
import logging
import re
from datetime import datetime
from urllib.parse import quote, urlsplit

from app.core.schemas import Followup, Input, UserError
from app.core.tool import Tool

from . import linkpeek

log = logging.getLogger("wa-bot.link")
tool = Tool("link", category="web", title="Link preview", emoji="🔗", description="Link previews")

SECTIONS = {
    "links": "links", "urls": "links", "outbound": "links",
    "contacts": "contacts", "contact": "contacts", "emails": "contacts", "email": "contacts", "social": "contacts", "socials": "contacts",
    "tech": "tech", "stack": "tech", "technology": "tech", "cms": "tech",
    "security": "security", "ssl": "security", "tls": "security", "whois": "security", "safe": "security", "domain": "security",
    "text": "text", "read": "text", "content": "text", "excerpt": "text", "summary": "text",
    "all": "all", "more": "all", "full": "all", "details": "all", "everything": "all",
}
SECTION = "(?:" + "|".join(sorted(SECTIONS, key=len, reverse=True)) + ")"
URL = (r"https?://[^\s<>\"']+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|dev|ai|app|co|pk|edu|gov|info|me|tv|news|blog|"
       r"xyz|tech|uk|us|in)(?:/\S*)?")
INPUTS = {"url": Input(required=True, pattern=URL, ask="🔗 Which link?"), "section": Input(pattern=SECTION)}


def _compact(n: int) -> str:
    for div, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= div:
            return f"{n / div:.1f}".rstrip("0").rstrip(".") + suffix
    return str(n)


async def _wikipedia(http, host: str, title: str, url: str) -> str:
    r = await http.get(f"https://{host}/api/rest_v1/page/summary/{quote(title, safe='%()_,')}")
    r.raise_for_status()
    page = r.json()
    meta = []
    if page.get("description"):
        meta.append(f"🏷️ {page['description']}")
    if page.get("type") == "disambiguation":
        meta.append("↔️ Disambiguation page — several topics share this name")
    if page.get("timestamp"):
        meta.append(f"📅 Last edited: {page['timestamp'][:10]}")
    if page.get("coordinates"):
        meta.append(f"📍 {page['coordinates']['lat']:.3f}, {page['coordinates']['lon']:.3f}")
    meta.append(f"🌍 Language: {host.split('.')[0]}")
    if page.get("wikibase_item"):
        meta.append(f"🗂️ Wikidata: {page['wikibase_item']}")
    if image := (page.get("thumbnail") or {}).get("source", ""):
        meta.append(f"🖼️ Image: {image}")
    extract = " ".join((page.get("extract") or "").split())
    return f"📚 *{page['title']}*\n{extract[:700]}\n\nℹ️ *Metadata*\n" + "\n".join(meta) + f"\n\n🔗 {url}"


async def _youtube(http, url: str) -> str:
    r = await http.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"})
    r.raise_for_status()
    d, info = r.json(), {}
    try:   # the watch page carries views, duration, publish date, category, description and tags
        html = (await linkpeek.fetch(url, max_bytes=1_500_000)).body.decode("utf-8", "ignore")
        for key, pat in (("views", r'"viewCount":"(\d+)"'), ("secs", r'"lengthSeconds":"(\d+)"'),
                         ("published", r'"publishDate":"([^"]+)"'), ("category", r'"category":"([^"]+)"')):
            if m := re.search(pat, html):
                info[key] = m.group(1)
        if m := re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', html):
            info["desc"] = json.loads(f'"{m.group(1)}"')
        if m := re.search(r'"keywords":\[((?:"(?:[^"\\]|\\.)*",?)+)\]', html):
            info["tags"] = json.loads(f"[{m.group(1)}]")[:6]
    except Exception:                                # noqa: BLE001 - the extras are optional
        log.info("youtube page details unavailable", exc_info=True)
    lines = [f"▶️ *{d['title']}*", f"📺 {d['author_name']}" + (f" ({d['author_url']})" if d.get("author_url") else "")]
    facts = []
    if info.get("views"):
        facts.append(f"👁️ {_compact(int(info['views']))} views")
    if info.get("secs"):
        s = int(info["secs"])
        facts.append(f"⏱️ {s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"⏱️ {s // 60}:{s % 60:02d}")
    if info.get("published"):
        facts.append(f"📅 {datetime.fromisoformat(info['published']).strftime('%d %b %Y')}")
    if info.get("category"):
        facts.append(f"🏷️ {info['category']}")
    if facts:
        lines.append(" · ".join(facts))
    if info.get("desc"):
        lines += ["", "📝 *Description*", " ".join(info["desc"].split())[:400]]
    if info.get("tags"):
        lines.append(f"\n🔖 Tags: {', '.join(info['tags'])}")
    if thumb := d.get("thumbnail_url", ""):
        lines.append(f"🖼️ Thumbnail: {thumb}")
    return "\n".join([*lines, "", f"🔗 {url}"])


async def _report(url: str) -> linkpeek.Report:
    try:
        return await linkpeek.get_report(url)
    except linkpeek.LinkError as e:
        raise UserError(str(e)) from None


async def _describe(http, url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    if host.endswith(".wikipedia.org") and parts.path.startswith("/wiki/"):
        return await _wikipedia(http, parts.hostname, parts.path[len("/wiki/"):], url)
    if host in ("youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"):
        return await _youtube(http, url)
    return linkpeek.summary(await _report(url))[0]


async def _section(name: str, r: linkpeek.Report) -> str:
    if name == "links":
        return linkpeek.section_links(r)
    if name == "contacts":
        return linkpeek.section_contacts(r)
    if name == "tech":
        return linkpeek.section_tech(r)
    if name == "text":
        return linkpeek.section_text(r)
    security = await linkpeek.section_security(r)
    if name == "security":
        return security
    return "\n\n〰️〰️〰️\n\n".join([linkpeek.summary(r)[0], linkpeek.section_links(r), linkpeek.section_contacts(r),
                                  linkpeek.section_tech(r), security])


@tool.feature(
    "peek", repeat="reuse", description="Page preview (add tech, security, links...)",
    phrases=["{url}", "link {url}", "peek {url}", "preview {url}", "summarize {url}", "summarise {url}", "what is {url}",
             "open {url}", "{section} of {url}", "{section} for {url}", "{url} {section}", "{section} {url}"],
    keywords=["link"],
    examples=["https://example.com", "summarize https://example.com", "tech of https://example.com"],
    inputs=INPUTS,
    followups=[Followup(phrases=["{section}", "show me {section}", "show me the {section}", "the {section}", "what about the {section}",
                                 "and the {section}", "{section} please"], overrides=["section"])])
async def peek(ctx, url, section):
    url = linkpeek.find_url(url)
    if not url:
        raise UserError("🔗 Send a full link, e.g. *https://example.com*.")
    if section:
        r = await _report(url)
        if not r.is_html:
            raise UserError("📎 That link is a file, not a web page — there's nothing more to show.")
        return await _section(SECTIONS[section.lower()], r)
    return await _describe(ctx.services.http, url)
