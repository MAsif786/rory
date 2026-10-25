"""Web search with Google's official Programmable Search API (GOOGLE_API_KEY + GOOGLE_CSE_ID in .env).
Without those keys users still get an answer (a Wikipedia lookup); the missing configuration is only ever logged, never shown."""
import logging
import os

from app.core.schemas import Followup, Input, UserError
from app.core.tool import Tool
from app.wikipedia import cut, page_url, summary

tool = Tool("search", category="web", title="Web search", emoji="🔎", description="Web search")

QUERY = r"(?!(?:i|me|my|you|your|we|us|our)\b)[^\n]{2,100}"
log = logging.getLogger("wa-bot.search")
_warned = False


async def _fallback(http, query: str) -> str:
    """No Google keys: answer from Wikipedia instead, or say plainly that nothing was found."""
    global _warned
    if not _warned:
        _warned = True
        log.warning("web search is not configured (set GOOGLE_API_KEY and GOOGLE_CSE_ID; free: 100 searches/day at "
                    "https://programmablesearchengine.google.com): answering from Wikipedia instead")
    try:
        page = await summary(http, query, missing=f"🔎 I couldn't find anything for *{query}*.")
    except UserError:
        raise UserError(f"🔎 I couldn't find anything for *{query}*. Try different words.") from None
    return f"🔎 *{page['title']}*\n{cut(page.get('extract'), 450)}\n\n🔗 {page_url(page)}"


@tool.feature(
    "web", description="Google search: top results with links", repeat="reuse",
    phrases=["google {query}", "google for {query}", "search {query}", "search for {query}", "search the web for {query}",
             "web search {query}", "search online for {query}", "look up {query} online", "find {query} online", "google search {query}"],
    keywords=["google"],
    examples=["google best pizza in lahore", "search for python tutorials"],
    negatives=["search history", "search engine optimization"],
    inputs={"query": Input(required=True, pattern=QUERY, ask="🔎 What should I search for?")},
    followups=[Followup(phrases=["what about {query}", "how about {query}", "and {query}"], overrides=["query"])])
async def web(ctx, query):
    key, cse = os.getenv("GOOGLE_API_KEY", "").strip(), os.getenv("GOOGLE_CSE_ID", "").strip()
    if not (key and cse):
        return await _fallback(ctx.services.http, query)
    r = await ctx.services.http.get("https://www.googleapis.com/customsearch/v1", params={"key": key, "cx": cse, "q": query, "num": 5})
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        raise UserError(f"🔎 No results for *{query}*.")
    lines = [f"🔎 *{query}*", ""]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. *{it['title']}*\n   {cut(it.get('snippet'), 140)}\n   {it['link']}")
    return "\n".join(lines)
