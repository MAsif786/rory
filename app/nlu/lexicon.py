"""Synonyms: unknown word -> a word the tools already understand.

Two sources, merged: this core table (chat abbreviations that mean the same everywhere) and each tool's own `synonyms={...}`
(`Tool("fun", synonyms={"gag": "joke"})`). The engine uses them only as a fallback or a challenger and only when the rewritten message
matches a declared phrase, so a synonym can widen what Rory understands but never invent an intent. Words a tool already uses are never
rewritten. Generate candidates for a new tool with `scripts/suggest_synonyms.py` (WordNet, development time only), then review them."""
import re

from app.core.schemas import FeatureSpec

CORE: dict[str, str] = {
    "temp": "temperature", "temps": "temperature", "abt": "about",
    "wat": "what", "wht": "what", "wats": "whats", "hw": "how", "whr": "where", "u": "you", "ur": "your", "r": "are",
}

MAX_SUBSTITUTIONS = 2                       # a message is rewritten in at most this many places (more means we are guessing)
_CACHE: dict[tuple, dict[str, str]] = {}


def lexicon(specs: list[FeatureSpec]) -> dict[str, str]:
    """Core table + every installed tool's synonyms. Cached per set of installed features."""
    key = tuple(s.full_name for s in specs)
    if key not in _CACHE:
        merged = dict(CORE)
        for s in specs:
            merged.update(dict(s.synonyms))
        _CACHE.clear()
        _CACHE[key] = merged
    return _CACHE[key]


def rewrite(text: str, table: dict[str, str], known: frozenset) -> tuple[str, list[tuple[str, str]]]:
    """Replace unknown words that have a synonym. Words the tools already know are left alone. Returns (new text, [(old, new)])."""
    out, changed = [], []
    for token in text.split():
        core = re.sub(r"^\W+|\W+$", "", token).lower()
        if core and core not in known and core in table and len(changed) < MAX_SUBSTITUTIONS:
            changed.append((core, table[core]))
            out.append(token.lower().replace(core, table[core]) if token.lower() != core else table[core])
        else:
            out.append(token)
    return " ".join(out), changed


def mentions_synonym(text: str, table: dict[str, str], known: frozenset) -> bool:
    return any((w := re.sub(r"^\W+|\W+$", "", t).lower()) in table and w not in known for t in text.split())
