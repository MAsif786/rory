"""Help and menu pages, generated from the registry: a new tool shows up here without touching this file.

Format:  <emoji> *Title*  →  blank line  →  body  →  blank line  →  optional "💡" hint.
"""
import difflib
import random
import re
from dataclasses import dataclass

from app.core.registry import Registry
from app.core.schemas import AGAIN
from app.nlu.entities import extract_dates
from app.core.schemas import FeatureSpec
from app.core.tool import Tool
from app.format import tip  # noqa: F401  (re-exported: tools and pages share one hint style)

MAX_EXAMPLES = 3


_LINKISH = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|org|net|io|dev|ai|app|co|pk|edu|gov|info|me)\b", re.I)


def shown(examples) -> list[str]:
    """Examples fit to show a user. One that looks like a link (https://example.com) is hidden: chat apps turn it into a clickable preview."""
    return [e for e in examples if not _LINKISH.search(e)]


def _about(tool: Tool) -> str:
    """The tool's one-line description, or "" when it only repeats the title ("Web search - Web search")."""
    t, d = tool.title.lower(), tool.description.lower()
    if not d or t in d or d in t or difflib.SequenceMatcher(None, t, d).ratio() >= 0.6:
        return ""
    return tool.description


def _examples(tool: Tool) -> list[str]:
    return shown(ex for f in tool.features.values() for ex in f.spec.examples)[:MAX_EXAMPLES]


def _is_game(tool: Tool) -> bool:
    return all(f.spec.kind == "session" for f in tool.features.values())


# How help is organised: a short home page lists these groups; `help <group>` opens one; `help <tool>` one tool; `help all` everything.
# (key, emoji, title, one-line description, aliases people might type). A tool joins a group with `Tool(..., category="<key>")`;
# a tool with no (or an unknown) category appears under "More" so it is never hidden.
CATEGORIES = [
    ("everyday", "🌤️", "Everyday", "weather, news, money, time and quick maths", ("tools", "daily", "utilities", "useful")),
    ("knowledge", "📚", "Look things up", "Wikipedia, countries, books and movies", ("lookup", "learn", "facts", "info", "reference")),
    ("islamic", "🕌", "Quran", "verses, search, recitation and tafsir", ("islam", "religion", "religious")),
    ("web", "🌐", "Web & dev", "GitHub, IP lookup, link previews and web search", ("dev", "developer", "internet", "online")),
    ("entertainment", "😄", "Just for fun", "jokes, facts, coin and dice", ("entertain", "funny", "jokes")),
    ("games", "🎮", "Games", "play against the bot", ("play", "game")),
    ("chat", "💬", "Chat", "say hi, thanks or goodbye", ("talk", "social", "greet")),
]
OTHER = ("other", "🧩", "More", "everything else", ())


def grouped(registry: Registry) -> list[tuple[tuple, list[Tool]]]:
    """[(category, tools)] in menu order, only non-empty groups; unknown categories land in More."""
    keys = {c[0] for c in CATEGORIES}
    by_key: dict[str, list[Tool]] = {}
    order = {name: i for i, name in enumerate(SHOWCASE)}
    for t in sorted((t for t in registry.tools.values() if not t.hidden), key=lambda t: (order.get(t.name, len(order)), t.name)):   # most useful first
        key = "games" if _is_game(t) else t.category if t.category in keys else "other"
        by_key.setdefault(key, []).append(t)
    return [(c, by_key[c[0]]) for c in (*CATEGORIES, OTHER) if c[0] in by_key]


def find_category(registry: Registry, word: str):
    word = word.strip().lower()
    for cat, tools in grouped(registry):
        if word in (cat[0], cat[2].lower(), *cat[4]):
            return cat, tools
    return None


def home_menu(registry: Registry) -> str:
    """A short page: one block per category (what is in it, and a few things to type), not one block per tool."""
    if not any(not t.hidden for t in registry.tools.values()):
        return "🏠 *Home*\n\nNo tools are installed yet."
    lines = ["🏠 *Home* — what would you like to do?", ""]
    groups = grouped(registry)
    for (key, emoji, title, _blurb, _aliases), tools in groups:
        if key == "games":
            names = " · ".join(t.title for t in tools[:4]) + (f" · +{len(tools) - 4} more" if len(tools) > 4 else "")
            lines += [f"{emoji} *{title}* — {names}", f"   _say *play {tools[0].name}* · or *games* for the list_"]
            continue
        names = " · ".join(t.title for t in tools) if len(tools) > 1 else (tools[0].description or tools[0].title)     # one tool: say what it does
        lines.append(f"{emoji} *{title}* — {names}")
        if ex := [e for t in tools for e in _examples(t)[:1]][:3]:
            lines.append("   _" + " · ".join(ex) + "_")
    return "\n".join(lines)


def category_page(registry: Registry, cat: tuple, tools: list[Tool]) -> str:
    key, emoji, title, blurb, _ = cat
    if key == "games":
        return games_menu(registry)
    lines = [f"{emoji} *{title}* — {blurb}", ""]
    for t in tools:
        lines.append(f"{t.emoji} *{t.title}* — {_about(t)}" if _about(t) else f"{t.emoji} *{t.title}*")
        if ex := _examples(t):
            lines.append("   _" + " · ".join(ex) + "_")
    return "\n".join(lines).rstrip()


def games_menu(registry: Registry) -> str:
    games = [t for t in registry.tools.values() if _is_game(t) and not t.hidden]
    if not games:
        return "🎮 *Games*\n\nNo games are installed yet."
    lines = ["🎮 *Games* — pick one:", ""]
    lines += [f"{g.emoji} *{g.title}*" + (f" — {_about(g)}" if _about(g) else "") + f"\n   _play {g.name}_" for g in games]
    return "\n".join(lines)


def repeated(reply: str, count: int) -> str:
    """The same lookup asked again within a minute: reuse the answer (no new API call) instead of repeating the work."""
    if count == 2:
        return f"🔁 Same as a moment ago:\n\n{reply}"
    return "😄 You've asked that a few times — nothing has changed. Anything else I can help with?"


ACKS = {"super", "nice", "cool", "great", "awesome", "wow", "good", "amazing", "perfect", "excellent", "wonderful", "fine", "ok", "okay",
        "k", "kk", "lol", "lmao", "haha", "hahaha", "yes", "yeah", "yep", "yup", "sure", "alright", "right", "hmm", "hmmm", "oh", "ohh",
        "ah", "aha", "mashallah", "alhamdulillah", "shabash", "acha", "theek hai", "no", "nope", "nah", "huh", "what", "why", "test",
        "testing", "👍", "🙏", "😂", "🙂", "😊"}
ACK_REPLIES = ["😊 Glad to hear it! Ask me anything else — send *help* for ideas.", "👍 Anytime! Send *help* if you want ideas.",
               "🙂 I'm here whenever you need something. Send *help* to see what I can do."]


AGAIN_WORDS = {p for p in AGAIN.phrases} | {"again please", "do it again", "repeat it"}
QUESTION_WORDS = {"what", "whats", "who", "whom", "why", "when", "where", "how", "which", "is", "are", "was", "were", "do", "does", "did",
                  "can", "could", "will", "would", "should", "tell", "show", "give", "and", "or", "but", "so"}


def _suggestion(registry: Registry, text: str) -> str | None:
    """The installed example closest to what was typed (a typo or a half-remembered phrase), if there is a close one."""
    wanted = " ".join(text.lower().split())
    examples = {ex.lower(): ex for s in registry.specs() for ex in shown(s.examples)}
    close = difflib.get_close_matches(wanted, list(examples), n=1, cutoff=0.7)
    return examples[close[0]] if close else None


@dataclass
class Unmatched:
    """What to say about a message nothing could handle, and how to file it in the improvement inbox."""
    reply: str
    kind: str = "unmatched"              # "unmatched" (not understood) | "out_of_scope" (understood, but not something Rory does)
    category: str | None = None          # for out_of_scope: which missing capability (reminders, music, orders...), counted by demand


# Things people ask a helper bot that Rory deliberately does not do (yet). Each is answered honestly and logged as demand for a new tool.
CAPABILITY_GAPS = [
    ("orders", r"\b(?:order|buy|purchase|book (?:me )?(?:a |an |the )?(?:taxi|cab|flight|ticket|tickets|table|hotel|room|ride))\b|\bwhere can i buy\b",
     "🛒 I can't place orders or make bookings."),
    ("reminders", r"\b(?:alarm|remind(?:er)?s?|timer|schedule|appointment)\b", "⏰ Reminders and alarms aren't available yet."),
    ("calls", r"^(?:please )?(?:call|phone|dial|ring)\b|\b(?:can|could|will|would) (?:you|u) (?:call|phone|ring)\b", "📞 I can't make calls."),
    ("messaging", r"\b(?:send|write|compose) (?:an? |the )?(?:e-?mail|sms|text|message|whatsapp)\b|\be-?mail\b", "✉️ I can't send messages for you."),
    ("music", r"\b(?:music|song|songs|spotify|playlist|play some)\b", "🎵 I can't play music."),
    ("smart_home", r"\bturn (?:on|off)\b|\b(?:lights?|thermostat|air conditioner|the (?:tv|fan|door))\b", "🏠 I can't control devices."),
    ("translation", r"\btranslat(?:e|ion)\b", "🌐 Translation isn't available yet."),
    ("writing", r"\bwrite (?:me )?(?:an? |the )?(?:poem|story|essay|letter|code|email|speech)\b|\b(?:poem|essay)\b", "✍️ I can't write long texts."),
    ("prices", r"\b(?:price|prices|rate|stock|stocks|share price|bitcoin|crypto|ethereum)\b", "📈 Prices and stocks aren't available yet."),
    ("scores", r"\b(?:score|scores|match|fixtures?|standings|cricket|football|ipl|psl)\b", "🏏 Live scores aren't available yet."),
    ("directions", r"\b(?:directions?|route|navigate|map|nearest|near me|distance (?:to|from))\b", "🗺️ Directions and maps aren't available yet."),
    ("help_with_tasks", r"\b(?:fix|repair|install|download|upload|delete|cancel)\b", "🔧 I can't do that kind of task."),
]
_CAPS = [(key, re.compile(rx, re.I), msg) for key, rx, msg in CAPABILITY_GAPS]
REQUEST = re.compile(r"^(?:(?:can|could|will|would) (?:you|u)\b|please\b|pls\b|i (?:want|need|wanna|would like|'d like)\b|(?:order|buy|book|call|send|set|turn|open|play|write|make|find|get|show|give|help|remind|translate|download|install|fix|create|schedule|cancel|delete|search)\b)", re.I)
QUESTION_START = re.compile(r"^(?:is|are|was|were|what|what's|whats|how|when|where|why|who|does|do|did|will|can|could)\b", re.I)
FIRST_PERSON = re.compile(r"^(?:i|im|i'm|i am|ive|i've|ill|i'll|my|me|we|our|it|its|it's|this|that|he|she|they)\b", re.I)
STATEMENT = re.compile(r"\b(?:is|are|was|were|am|has|have|had|love|loved|like|liked|hate|hated|enjoy|enjoyed)\b", re.I)
ABOUT_BOT = re.compile(r"^(?:what(?:'s| is) your|do you (?:like|have|know|eat|sleep|love|think)|are you|your (?:name|age|favou?rite)|how old are you|where (?:do you|are you))", re.I)


SHOWCASE = ["weather", "news", "currency", "units", "calc", "clock", "wiki", "country", "book", "movie", "quran", "fun", "dice"]     # what to mention first


def _can_do(registry: Registry) -> str:
    """One line of what Rory can do, most useful first (not alphabetical: a list starting with 'books, calculator' undersells it)."""
    order = {name: i for i, name in enumerate(SHOWCASE)}
    tools = sorted((t for t in registry.tools.values() if not _is_game(t) and not t.hidden), key=lambda t: (order.get(t.name, len(order)), t.name))
    names = ", ".join(t.title.lower() for t in tools[:7])
    games = " and games" if any(_is_game(t) for t in registry.tools.values()) else ""
    return f"I can help with {names}{games}."


def classify_unmatched(registry: Registry, times: int = 1, text: str = "") -> Unmatched:
    """The fallback when nothing matched. It tries to be useful: acknowledge small talk, suggest a close example for a typo,
    say plainly when a request is outside what Rory does (and count it as demand), offer a Wikipedia lookup for a short unknown word,
    or show real examples. Asked again: say so, don't repeat."""
    clean = " ".join(re.sub(r"[^\w\s👍🙏😂🙂😊']", "", text.lower()).split())
    category = next(((k, msg) for k, rx, msg in _CAPS if rx.search(clean)), None)
    # a request, or a short noun phrase / question about something Rory doesn't do ("bitcoin price", "is bitcoin going up"): never a statement
    asks = bool(REQUEST.match(clean)) or (category is not None and not ABOUT_BOT.match(clean) and (
        bool(QUESTION_START.match(clean)) or (len(clean.split()) <= 6 and not FIRST_PERSON.match(clean) and not STATEMENT.search(clean))))
    if times > 1:
        if asks:
            return Unmatched(f"🙏 That's still something I can't do. {_can_do(registry)} Send *help* for the full list.", "out_of_scope", category[0] if category else None)
        return Unmatched("🤔 Still not sure what you mean. Try rephrasing, or send *help* to see what I can do.")
    if clean in ACKS:
        return Unmatched(random.choice(ACK_REPLIES))
    if clean in AGAIN_WORDS:                                          # "again" / "one more" with nothing to repeat (the context expired, or the last answer can't repeat)
        return Unmatched("🔁 Again what? I've lost track of what we were doing.\n\n" + tip("Ask in full, e.g. _flip a coin_ or _tell me a joke_"))
    if close := _suggestion(registry, text):
        return Unmatched(f"🤔 I didn't get that. Did you mean _{close}_?")
    if ABOUT_BOT.match(clean):
        return Unmatched("😄 I'm just a helper bot, so no favourites or feelings to share! Ask me something I can look up or work out — send *help* to see what.",
                         "out_of_scope", "about_bot")
    if asks:
        first = f"{category[1]} " if category else "🙏 That's outside what I can do right now. "
        return Unmatched(f"{first}{_can_do(registry)}\n\n{tip('Send *help* to see everything')}", "out_of_scope", category[0] if category else None)
    if re.match(r"^(?:i|im|i'm|i am|ive|i've|ill|i'll|my|me|we|our|you|your|youre|you're|it|its|it's|this|that)\b", clean) or STATEMENT.search(clean):
        return Unmatched("🙂 Thanks for telling me! I'm best with questions and little tasks — send *help* to see what I can do.")
    if clean:
        left, found = extract_dates(re.sub(r"^(?:and|also|what about|how about|then)\s+", "", clean))
        if found and not left.strip():                              # only a date: "and tomorrow", "next monday", "the weekend"
            return Unmatched(f"📅 {found['when'].capitalize()} for what? I've lost track of what we were talking about.\n\n"
                             + tip(f"Ask in full, e.g. _weather {found['when']} in lahore_ — or send *help* to see what I can do"))
    if m := re.match(r"^(?:what|how) about (.+)$", clean):          # a follow-up with nothing to follow
        return Unmatched(f"🤔 What about *{m.group(1)}*? I've lost track of what we were talking about.\n\n"
                         + tip(f"Ask in full, e.g. _weather in {m.group(1)}_ — or send *help* to see what I can do"))
    if (0 < len(clean.split()) <= 3 and clean.replace(" ", "").isalpha() and "wiki" in registry.tools
            and clean.split()[0] not in QUESTION_WORDS):
        return Unmatched(f"🤔 I don't know *{clean}* yet.\n\n"
                         + tip(f"Send _tell me about {clean}_ to look it up on Wikipedia, or *help* to see what I can do"))
    answers = [t for t in registry.tools.values() if any(f.spec.kind == "answer" for f in t.features.values())]
    examples = [ex for t in answers for ex in _examples(t)[:1]][:4]
    hint = ("Try " + " · ".join(f"_{e}_" for e in examples) + " — or send *menu*") if examples else "Send *menu* to see what I can do"
    return Unmatched(f"🤔 I didn't get that.\n\n{tip(hint)}")


def not_understood(registry: Registry, times: int = 1, text: str = "") -> str:
    return classify_unmatched(registry, times, text).reply


def _feature_lines(spec: FeatureSpec) -> list[str]:
    out = [f"• *{spec.full_name}*" + (f" — {spec.description}" if spec.description else "")]
    if ex := shown(spec.examples):
        out.append("   _" + " · ".join(ex[:MAX_EXAMPLES]) + "_")
    return out


def tool_page(tool: Tool) -> str:
    lines = [f"{tool.emoji} *{tool.title}*" + (f" — {_about(tool)}" if _about(tool) else ""), ""]
    for f in tool.features.values():
        lines += _feature_lines(f.spec)
    return "\n".join(lines)


def feature_page(spec: FeatureSpec) -> str:
    lines = [f"*{spec.full_name}*"]
    if spec.description:
        lines.append(spec.description)
    if spec.inputs:
        lines.append("Needs: " + ", ".join(f"{n}{'' if i.required else ' (optional)'}" for n, i in spec.inputs.items()))
    if ex := shown(spec.examples):
        lines.append("Try: _" + " · ".join(ex[:MAX_EXAMPLES]) + "_")
    lines.append(f"_part of the *{spec.tool}* tool_")
    return "\n".join(lines)


def full_help(registry: Registry) -> str:
    """The complete index, grouped: every tool with the names of its features (examples live one level down, in `help <tool>`).
    Compact on purpose: a full listing with examples is several thousand characters and would be cut off by the message length cap."""
    if not registry.tools:
        return home_menu(registry)
    blocks = []
    for (key, emoji, title, _b, _a), tools in grouped(registry):
        rows = [f"{t.emoji} *{t.title}* — " + " · ".join(f.spec.name.replace("_", " ") for f in t.features.values()) for t in tools]
        blocks.append("\n".join([f"━━ {emoji} *{title.upper()}* ━━", *rows]))
    blocks.append(tip("*help <tool>* shows a tool's features with examples (e.g. *help weather*) · *help <tool>.<feature>* explains one"))
    return "\n\n".join(blocks)


def help_for(registry: Registry, arg: str) -> str:
    """`help`, `help all`, `help everyday` (a group), `help weather` (a tool), `help weather.current` or `help forecast` (a feature)."""
    arg = arg.strip().lower().lstrip("!/")
    if not arg:
        return home_menu(registry)
    if arg == "all":
        return full_help(registry)
    if tool := registry.tools.get(arg):                           # a tool's own name wins over a group word ("fun", "quran")
        return tool_page(tool)
    if found := find_category(registry, arg):
        return category_page(registry, *found)
    specs = registry.specs()
    hits = [s for s in specs if arg in (s.full_name, s.name)]
    if len(hits) == 1:
        return feature_page(hits[0])
    return f"🤷 No group, tool or feature called *{arg}*. Send *help* for the groups or *help all* for everything."
