"""Wikipedia lookups shared by tools (wiki, movie)."""
from urllib.parse import quote

from app.core.schemas import UserError


def cut(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


async def summary(http, query: str, *, suffix: str = "", missing: str = "") -> dict:
    """Best-matching article's REST summary. `http` is ctx.services.http."""
    r = await http.get("https://en.wikipedia.org/w/api.php", params={
        "action": "query", "list": "search", "srsearch": f"{query} {suffix}".strip(), "srlimit": 1, "format": "json"})
    r.raise_for_status()
    hits = r.json().get("query", {}).get("search", [])
    if not hits:
        raise UserError(missing or f"📚 Wikipedia has nothing for *{query}*.")
    r = await http.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(hits[0]['title'].replace(' ', '_'), safe='')}")
    r.raise_for_status()
    return r.json()


def page_url(page: dict) -> str:
    return page.get("content_urls", {}).get("desktop", {}).get("page", "")
