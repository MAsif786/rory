"""Types messages the way people actually type them. Seeded, so a failure is reproducible: the same seed always makes the same mess.

Each noise is a function text -> text. `variants(text, rng, n)` returns n different messy versions of a message, each with 1-2 noises, plus
the name of the noises used so a failure report can say WHICH kind of mess broke the bot."""
import random
import re

QWERTY = {"q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh", "u": "yij", "i": "uok", "o": "ipl", "p": "ol", "a": "qsz", "s": "adwx",
          "d": "sfec", "f": "dgrv", "g": "fhtb", "h": "gjyn", "j": "hkum", "k": "jli", "l": "kop", "z": "ax", "x": "zcs", "c": "xvd", "v": "cfb", "b": "vgn",
          "n": "bhm", "m": "nj"}
FILLER_BEFORE = ["pls", "please", "hey", "hi rory", "bro", "yaar", "ok", "so", "um", "can you", "could you", "i want to", "zara", "rory", "hey rory", "oye"]
FILLER_AFTER = ["please", "pls", "thanks", "bro", "yaar", "now", "asap", "plz", "rory", "ji", "thx", "?", "!!", "..."]
EMOJI = ["😊", "🙏", "🔥", "😂", "👍", "🙂", "😅"]


def _words(text):
    return [m for m in re.finditer(r"[A-Za-z']{4,}", text)]


def _edit(text, rng, fn):
    words = _words(text)
    if not words:
        return text
    m = rng.choice(words)
    return text[: m.start()] + fn(m.group(0), rng) + text[m.end():]


def swap(text, rng):
    def f(w, r):
        i = r.randrange(1, len(w) - 1)
        return w[:i] + w[i + 1] + w[i] + w[i + 2:] if len(w) > 3 else w
    return _edit(text, rng, f)


def drop(text, rng):
    return _edit(text, rng, lambda w, r: (lambda i: w[:i] + w[i + 1:])(r.randrange(1, len(w) - 1)))


def duplicate(text, rng):
    return _edit(text, rng, lambda w, r: (lambda i: w[:i] + w[i] + w[i:])(r.randrange(1, len(w) - 1)))


def neighbour(text, rng):
    def f(w, r):
        i = r.randrange(1, len(w) - 1)
        c = w[i].lower()
        return w[:i] + (r.choice(QWERTY[c]) if c in QWERTY else w[i]) + w[i + 1:]
    return _edit(text, rng, f)


def lower(text, rng):
    return text.lower()


def upper(text, rng):
    return text.upper()


def title(text, rng):
    return text.title()


def no_punctuation(text, rng):
    """People drop question marks, exclamations and the final full stop. They do not delete the dots of an IP address or the colon of 2:255."""
    return re.sub(r"[?!]|\.$", "", text)


def extra_punctuation(text, rng):
    return text + rng.choice(["?", "!!", "...", "??", " ?!"])


def no_apostrophes(text, rng):
    return text.replace("'", "").replace("’", "")


def filler_before(text, rng):
    return f"{rng.choice(FILLER_BEFORE)} {text}"


def filler_after(text, rng):
    return f"{text} {rng.choice(FILLER_AFTER)}".replace(" ?", "?")


def elongate(text, rng):
    return _edit(text, rng, lambda w, r: w + w[-1] * r.randint(1, 3))


def double_spaces(text, rng):
    return "  " + text.replace(" ", "  ", 1) + " "


def emoji(text, rng):
    return f"{text} {rng.choice(EMOJI)}"


NOISES = {fn.__name__: fn for fn in (swap, drop, duplicate, neighbour, lower, upper, title, no_punctuation, extra_punctuation, no_apostrophes,
                                      filler_before, filler_after, elongate, double_spaces, emoji)}
TYPOS = {"swap", "drop", "duplicate", "neighbour", "elongate"}


def variants(text: str, rng: random.Random, n: int = 8, only: list[str] | None = None) -> list[tuple[str, tuple[str, ...]]]:
    """n messy versions of `text`: [(messy text, (noise names...))]. Never returns the original unchanged."""
    names, out, guard = only or list(NOISES), [], 0
    while len(out) < n and guard < n * 20:
        guard += 1
        used = tuple(rng.sample(names, min(rng.choice([1, 1, 2]), len(names))))
        messy = text
        for name in used:
            messy = NOISES[name](messy, rng)
        if messy.strip() and messy != text and (messy, used) not in out:
            out.append((messy, used))
    return out
