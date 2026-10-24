"""Movie info: TMDB if TMDB_API_KEY is set, otherwise Wikipedia."""
import os

from app.core.schemas import Followup, Input, UserError
from app.core.tool import Tool
from app.wikipedia import cut, page_url, summary

tool = Tool("movie", title="Movies", emoji="🎬", description="Movie info and ratings")

TITLE = (r"(?!(?:i|me|my|you|your|we|us|our|it|this|that|these|those|there|was|is|are|were|has|have|had|what|who|how|why|when|where|which)\b)"
         r"[^\n]{1,80}(?<!\ba)(?<!\ban)(?<!\bthe)(?<!\bis)(?<!\bwas)(?<!\bare)(?<!\bwere)(?<!\bto)(?<!\bof)(?<!\band)(?<!\bor)")


@tool.feature(
    "info", repeat="reuse", description="Movie info (ratings with a TMDB key, else a Wikipedia summary)",
    phrases=["movie {title}", "film {title}", "the movie {title}", "the film {title}", "{title} movie", "{title} film",
             "tell me about the movie {title}", "tell me about the film {title}", "is {title} a good movie", "is {title} a good film",
             "is {title} worth watching", "info on the movie {title}"],
    keywords=["movie", "film"],
    examples=["movie Inception", "is Inception a good movie"],
    negatives=["movie night", "movie ticket", "movie tickets", "movie theatre", "movie theater", "movie time", "movie marathon",
               "movie plan", "movies tonight", "film festival", "watch a movie", "go to the movie", "go to a movie", "see a movie"],
    inputs={"title": Input(required=True, pattern=TITLE, ask="🎬 Which movie?")},
    followups=[Followup(phrases=["what about {title}", "how about {title}"], overrides=["title"])])
async def info(ctx, title):
    http, key = ctx.services.http, os.getenv("TMDB_API_KEY", "").strip()
    if not key:
        page = await summary(http, title, suffix="film", missing=f"🎬 No movie found for *{title}*.")
        return (f"🎬 *{page['title']}*\n{cut(page.get('extract'), 450)}\n\n🔗 {page_url(page)}")
    headers, params = {}, {"query": title}
    if len(key) > 40:                                # v4 read-access token
        headers["Authorization"] = f"Bearer {key}"
    else:
        params["api_key"] = key
    r = await http.get("https://api.themoviedb.org/3/search/movie", params=params, headers=headers)
    r.raise_for_status()
    results = r.json().get("results")
    if not results:
        raise UserError(f"🎬 No movie found for *{title}*.")
    m = results[0]
    return (f"🎬 *{m['title']}* ({(m.get('release_date') or '')[:4] or '?'})\n"
            f"⭐ {m.get('vote_average', 0):.1f}/10 ({m.get('vote_count', 0):,} votes)\n\n"
            f"{cut(m.get('overview'), 350)}\n\n🔗 https://www.themoviedb.org/movie/{m['id']}")
