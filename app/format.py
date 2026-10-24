"""Smart formatting for outgoing messages: shared helpers for tools, and one final tidy-up for every reply."""
import re

MAX_LEN = 3800                      # WhatsApp allows far more, but long walls of text are unreadable; cut at a paragraph
NUM_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def num(i: int) -> str:
    """1 -> 1️⃣ (1-based), falling back to "11." past ten."""
    return NUM_EMOJI[i - 1] if 1 <= i <= len(NUM_EMOJI) else f"{i}."


def title(emoji: str, text: str) -> str:
    return f"{emoji} *{text}*"


def tip(text: str) -> str:
    return f"💡 {text}"


def numbered(items: list[tuple[str, str]]) -> list[str]:
    """[(headline, detail)] -> lines like "1️⃣ *headline*" with an indented italic detail line."""
    out = []
    for i, (head, detail) in enumerate(items, 1):
        out.append(f"{num(i)} *{head}*")
        if detail:
            out.append(f"     _{detail}_")
    return out


def tidy(text: str) -> str:
    """Final pass on every reply: WhatsApp-style emphasis, no stray whitespace, never an overlong message."""
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)                      # **bold** -> *bold*
    text = re.sub(r"(?m)^#{1,6}[ \t]+(.+?)[ \t]*$", r"*\1*", text)           # "## Heading" -> *Heading*
    text = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
    if len(text) > MAX_LEN:
        cut = text[:MAX_LEN]
        for sep in ("\n\n", "\n", " "):
            if (i := cut.rfind(sep)) > MAX_LEN * 0.6:
                cut = cut[:i]
                break
        text = cut.rstrip() + "\n\n… _(shortened)_"
    return text
