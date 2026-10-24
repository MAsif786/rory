"""Book info from Open Library."""
from app.core.schemas import Followup, Input, UserError
from app.core.tool import Tool

tool = Tool("book", title="Books", emoji="📖", description="Look up books and authors")

TITLE = (r"(?!(?:i|me|my|you|your|we|us|our|it|this|that|these|those|there|was|is|are|were|has|have|had|what|who|how|why|when|where|which)\b)"
         r"[^\n]{1,80}(?<!\ba)(?<!\ban)(?<!\bthe)(?<!\bis)(?<!\bwas)(?<!\bare)(?<!\bwere)(?<!\bto)(?<!\bof)(?<!\band)(?<!\bor)")


@tool.feature(
    "info", repeat="reuse", description="Book info from Open Library (who wrote Dune, book 1984)",
    phrases=["book {title}", "the book {title}", "novel {title}", "who wrote {title}", "who is the author of {title}",
             "author of {title}", "tell me about the book {title}", "{title} book", "{title} novel"],
    keywords=["novel", "isbn"],
    examples=["who wrote Dune", "book 1984"],
    negatives=["book a ", "book an ", "book me", "book us", "book my", "book the flight", "book tickets", "book table", "book room",
               "book hotel", "book flight", "book club", "book store", "book shop", "book shelf", "book fair", "book week",
               "book now", "to book", "address book", "phone book", "face book", "facebook", "note book", "notebook"],
    inputs={"title": Input(required=True, pattern=TITLE, ask="📖 Which book?")},
    followups=[Followup(phrases=["what about {title}", "how about {title}"], overrides=["title"])])
async def info(ctx, title):
    r = await ctx.services.http.get("https://openlibrary.org/search.json", params={
        "q": title, "limit": 1, "fields": "key,title,author_name,first_publish_year,number_of_pages_median,ratings_average,subject"})
    r.raise_for_status()
    docs = r.json().get("docs")
    if not docs:
        raise UserError(f"📚 No book found for *{title}*.")
    b = docs[0]
    lines = [f"📖 *{b['title']}*", f"✍️ {', '.join(b.get('author_name', ['Unknown'])[:3])}"]
    if b.get("first_publish_year"):
        lines.append(f"📅 First published {b['first_publish_year']}")
    if b.get("number_of_pages_median"):
        lines.append(f"📄 ~{b['number_of_pages_median']} pages")
    if b.get("ratings_average"):
        lines.append(f"⭐ {b['ratings_average']:.1f}/5")
    subjects = list(dict.fromkeys(x.strip().lower() for x in b.get("subject", []) if len(x) < 30))[:4]
    if subjects:
        lines.append(f"🏷️ {', '.join(subjects)}")
    lines.append(f"🔗 https://openlibrary.org{b['key']}")
    return "\n".join(lines)
