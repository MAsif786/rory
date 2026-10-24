"""Web search with Google's official Programmable Search API (needs GOOGLE_API_KEY and GOOGLE_CSE_ID in .env)."""
import os

from app.core.schemas import Followup, Input, UserError
from app.core.tool import Tool
from app.wikipedia import cut

tool = Tool("search", title="Web search", emoji="🔎", description="Search the web with Google")

QUERY = r"(?!(?:i|me|my|you|your|we|us|our)\b)[^\n]{2,100}"
SETUP = ("🔎 Web search isn't set up yet. Add *GOOGLE_API_KEY* and *GOOGLE_CSE_ID* to the bot's .env "
         "(free: 100 searches a day — https://programmablesearchengine.google.com).")


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
        raise UserError(SETUP)
    r = await ctx.services.http.get("https://www.googleapis.com/customsearch/v1", params={"key": key, "cx": cse, "q": query, "num": 5})
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        raise UserError(f"🔎 No results for *{query}*.")
    lines = [f"🔎 *{query}*", ""]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. *{it['title']}*\n   {cut(it.get('snippet'), 140)}\n   {it['link']}")
    return "\n".join(lines)
