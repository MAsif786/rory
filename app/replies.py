"""Help and menu pages, generated from the registry: a new tool shows up here without touching this file.

Format:  <emoji> *Title*  →  blank line  →  body  →  blank line  →  optional "💡" hint.
"""
import difflib
import random
import re

from app.core.registry import Registry
from app.core.schemas import FeatureSpec
from app.core.tool import Tool
from app.format import tip  # noqa: F401  (re-exported: tools and pages share one hint style)

MAX_EXAMPLES = 3


def _examples(tool: Tool) -> list[str]:
    return [ex for f in tool.features.values() for ex in f.spec.examples][:MAX_EXAMPLES]


def _is_game(tool: Tool) -> bool:
    return all(f.spec.kind == "session" for f in tool.features.values())


def home_menu(registry: Registry) -> str:
    if not registry.tools:
        return "🏠 *Home*\n\nNo tools are installed yet."
    lines = ["🏠 *Home* — what would you like to do?", ""]
    games = [t for t in registry.tools.values() if _is_game(t)]
    for t in registry.tools.values():
        if _is_game(t):
            continue
        lines.append(f"{t.emoji} *{t.title}*" + (f" — {t.description}" if t.description else ""))
        if ex := _examples(t):
            lines.append("   _" + " · ".join(ex) + "_")
    if games:
        lines += ["", "🎮 *Games* — say *play* and a game name:", "   " + " · ".join(f"{g.emoji} {g.title}" for g in games)]
    lines += ["", tip("*help weather* shows a tool's features · *help all* lists everything")]
    return "\n".join(lines)


def games_menu(registry: Registry) -> str:
    games = [t for t in registry.tools.values() if _is_game(t)]
    if not games:
        return "🎮 *Games*\n\nNo games are installed yet."
    lines = ["🎮 *Games* — pick one:", ""]
    lines += [f"{g.emoji} *{g.title}* — {g.description}\n   _play {g.name}_" for g in games]
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


QUESTION_WORDS = {"what", "whats", "who", "whom", "why", "when", "where", "how", "which", "is", "are", "was", "were", "do", "does", "did",
                  "can", "could", "will", "would", "should", "tell", "show", "give", "and", "or", "but", "so"}


def _suggestion(registry: Registry, text: str) -> str | None:
    """The installed example closest to what was typed (a typo or a half-remembered phrase), if there is a close one."""
    wanted = " ".join(text.lower().split())
    examples = {ex.lower(): ex for s in registry.specs() for ex in s.examples}
    close = difflib.get_close_matches(wanted, list(examples), n=1, cutoff=0.7)
    return examples[close[0]] if close else None


def not_understood(registry: Registry, times: int = 1, text: str = "") -> str:
    """The fallback when nothing matched. It tries to be useful: acknowledge small talk, suggest a close example for a
    typo, offer a Wikipedia lookup for a short unknown word, or show real examples. Asked again: say so, don't repeat."""
    clean = " ".join(re.sub(r"[^\w\s👍🙏😂🙂😊]", "", text.lower()).split())
    if times > 1:
        return "🤔 Still not sure what you mean. Try rephrasing, or send *help* to see what I can do."
    if clean in ACKS:
        return random.choice(ACK_REPLIES)
    if close := _suggestion(registry, text):
        return f"🤔 I didn't get that. Did you mean _{close}_?"
    if m := re.match(r"^(?:what|how) about (.+)$", clean):          # a follow-up with nothing to follow
        return (f"🤔 What about *{m.group(1)}*? I've lost track of what we were talking about.\n\n"
                + tip(f"Ask in full, e.g. _weather in {m.group(1)}_ — or send *help* to see what I can do"))
    if (0 < len(clean.split()) <= 3 and clean.replace(" ", "").isalpha() and "wiki" in registry.tools
            and clean.split()[0] not in QUESTION_WORDS):
        return (f"🤔 I don't know *{clean}* yet.\n\n"
                + tip(f"Send _tell me about {clean}_ to look it up on Wikipedia, or *help* to see what I can do"))
    answers = [t for t in registry.tools.values() if any(f.spec.kind == "answer" for f in t.features.values())]
    examples = [ex for t in answers for ex in _examples(t)[:1]][:4]
    hint = ("Try " + " · ".join(f"_{e}_" for e in examples) + " — or send *menu*") if examples else "Send *menu* to see what I can do"
    return f"🤔 I didn't get that.\n\n{tip(hint)}"


def _feature_lines(spec: FeatureSpec) -> list[str]:
    out = [f"• *{spec.full_name}*" + (f" — {spec.description}" if spec.description else "")]
    if spec.examples:
        out.append("   _" + " · ".join(spec.examples[:MAX_EXAMPLES]) + "_")
    return out


def tool_page(tool: Tool) -> str:
    lines = [f"{tool.emoji} *{tool.title}*" + (f" — {tool.description}" if tool.description else ""), ""]
    for f in tool.features.values():
        lines += _feature_lines(f.spec)
    return "\n".join(lines)


def feature_page(spec: FeatureSpec) -> str:
    lines = [f"*{spec.full_name}*"]
    if spec.description:
        lines.append(spec.description)
    if spec.inputs:
        lines.append("Needs: " + ", ".join(f"{n}{'' if i.required else ' (optional)'}" for n, i in spec.inputs.items()))
    if spec.examples:
        lines.append("Try: _" + " · ".join(spec.examples[:MAX_EXAMPLES]) + "_")
    lines.append(f"_part of the *{spec.tool}* tool_")
    return "\n".join(lines)


def full_help(registry: Registry) -> str:
    if not registry.tools:
        return home_menu(registry)
    return "\n\n".join(tool_page(t) for t in registry.tools.values())


def help_for(registry: Registry, arg: str) -> str:
    """`help`, `help all`, `help weather` (a tool), `help weather.current` or `help forecast` (a feature)."""
    arg = arg.strip().lower().lstrip("!/")
    if not arg:
        return home_menu(registry)
    if arg == "all":
        return full_help(registry)
    if tool := registry.tools.get(arg):
        return tool_page(tool)
    specs = registry.specs()
    hits = [s for s in specs if arg in (s.full_name, s.name)]
    if len(hits) == 1:
        return feature_page(hits[0])
    return f"🤷 No tool or feature called *{arg}*. Send *help all* for the full list."
