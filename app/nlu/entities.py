"""Entity pre-pass: lift dates and spoken maths out of a message so the phrase matcher sees a clean sentence.

    "weather next monday in karachi"   ->  ("weather in karachi", when="next monday")
    "what's fifteen plus four"          ->  "what's 15 + 4"
    "square root of 144"                ->  "sqrt(144)"

Without this a free-text slot swallows the date ("place = next monday in karachi"). The engine only trusts these rewrites when the
feature that matches the clean text can actually use them (a `when` input, or the calculator)."""
import re
from datetime import date

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WD = "|".join(WEEKDAYS)
_CONNECT = r"(?:(?:for|on|during|at|by|until|till)\s+)?"
# (regex, label). Longest / most specific first; each consumes its own connector words ("for the weekend", "on monday").
_DATES = [
    (rf"{_CONNECT}(?:the\s+)?day\s+after\s+tomorrow|parson", "day after tomorrow"),
    (rf"{_CONNECT}(?:tomorrow|tmrw|tmr|kal)", "tomorrow"),
    (rf"{_CONNECT}tonight", "tonight"),
    (rf"{_CONNECT}(?:today|aaj(?:\s+(?:ka|ki|ke))?)", "today"),
    (rf"{_CONNECT}(?:(?:this|the|next|coming)\s+)?weekend", "weekend"),
    (rf"{_CONNECT}(?:in\s+(\d{{1,2}})\s+days?|(\d{{1,2}})\s+days?\s+from\s+now)", "in N days"),
    (rf"{_CONNECT}next\s+week", "next week"),
    (rf"{_CONNECT}(?:(next|this|coming)\s+)?({_WD})", "weekday"),
]
_COMPILED = [(re.compile(rf"\b(?:{p})\b", re.I), label) for p, label in _DATES]


DATE_WORDS = (r"day after tomorrow|tomorrow|tonight|today|weekend|next week|in \d{1,2} days|"
              rf"(?:(?:next|this|coming) )?(?:{_WD})")     # for Input(pattern=...) in follow-ups like "and {when}"


def extract_dates(text: str) -> tuple[str, dict]:
    """Remove the first date expression. Returns (clean text, {"when": label}) or (text, {}) when there is none."""
    for rx, label in _COMPILED:
        if m := rx.search(text):
            if label == "in N days":
                label = f"in {m.group(1) or m.group(2)} days"
            elif label == "weekday":
                label = f"{m.group(1) + ' ' if m.group(1) and m.group(1).lower() == 'next' else ''}{m.group(2).lower()}"
            clean = " ".join((text[: m.start()] + " " + text[m.end():]).split())
            return clean.strip(" ,"), {"when": label}
    return text, {}


def days_ahead(label: str, today: date | None = None) -> int | None:
    """How many days from today a `when` label is (0 = today). None for labels we cannot place."""
    today = today or date.today()
    label = (label or "").lower().strip()
    if label in ("", "today", "tonight"):
        return 0
    if label == "tomorrow":
        return 1
    if label == "day after tomorrow":
        return 2
    if label == "next week":
        return 7
    if label == "weekend":
        return (5 - today.weekday()) % 7 if today.weekday() < 5 else 0         # the coming Saturday (0 if it is already the weekend)
    if m := re.fullmatch(r"in (\d{1,2}) days", label):
        return int(m.group(1))
    name = label.removeprefix("next ")
    if name in WEEKDAYS:
        ahead = (WEEKDAYS.index(name) - today.weekday()) % 7
        return 7 if ahead == 0 and label.startswith("next ") else ahead
    return None


def describe(label: str, today: date | None = None) -> str:
    """Human wording for a `when` label: 'tomorrow', 'Monday 26 Oct'."""
    today, ahead = today or date.today(), days_ahead(label, today)
    if ahead in (None, 0):
        return "today"
    if ahead == 1:
        return "tomorrow"
    from datetime import timedelta
    return (today + timedelta(days=ahead)).strftime("%A %d %b")


# --- spoken maths ----------------------------------------------------------------------------------------------------------
_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                                     "sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 10**6}
_NUMBER_WORD = set(_UNITS) | set(_TENS) | set(_SCALES)


def words_to_numbers(text: str) -> str:
    """'fifteen' -> '15', 'twenty five' -> '25', 'one hundred and five' -> '105'. Other words are left untouched."""
    tokens, out, i = text.split(), [], 0
    while i < len(tokens):
        if re.sub(r"\W", "", tokens[i]).lower() in _NUMBER_WORD:
            total = current = 0
            used = 0
            while i < len(tokens):
                w = re.sub(r"\W", "", tokens[i]).lower()
                if w in _UNITS:
                    current += _UNITS[w]
                elif w in _TENS:
                    current += _TENS[w]
                elif w in _SCALES:
                    if w == "hundred":
                        current = max(current, 1) * 100
                    else:
                        total += max(current, 1) * _SCALES[w]
                        current = 0
                elif w == "and" and used and i + 1 < len(tokens) and re.sub(r"\W", "", tokens[i + 1]).lower() in _NUMBER_WORD:
                    pass
                else:
                    break
                used += 1
                i += 1
            out.append(str(total + current))
        else:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


_NUM = r"(\d+(?:\.\d+)?)"
_OPS = [
    (rf"\bsquare\s+root\s+of\s+{_NUM}", r"sqrt(\1)"), (rf"\b{_NUM}\s+squared\b", r"\1**2"), (rf"\b{_NUM}\s+cubed\b", r"\1**3"),
    (r"\b(?:to\s+the\s+power\s+of|raised\s+to(?:\s+the\s+power\s+of)?)\b", "**"),
    (r"\b(?:multiplied\s+by|times)\b", "*"), (r"\b(?:divided\s+by|over)\b", "/"),
    (r"\b(?:plus|added\s+to)\b", "+"), (r"\b(?:minus|subtract(?:ed)?(?:\s+by)?|less)\b", "-"),
]


def spoken_maths(text: str) -> str:
    """Rewrite spoken arithmetic with symbols; returns the text unchanged when it does not look like maths."""
    out = words_to_numbers(text)
    for rx, repl in _OPS:
        out = re.sub(rx, repl, out, flags=re.I)
    out = " ".join(out.split())
    return out if out != text and re.search(r"\d", out) else text
