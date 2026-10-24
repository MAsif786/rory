"""Rule-based engine: matches messages against the phrases/keywords/negatives/followups tools declare."""
import difflib
import re
from functools import lru_cache

from app.core.schemas import FeatureSpec, Input
from app.intent.decision import Decision, LastTurn

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def normalize(text: str) -> str:
    return " ".join(text.lower().strip().rstrip(".!?؟ ").split())


def _lit(text: str) -> str:
    """Escaped literal text where an apostrophe is optional, so "what's" also matches "whats" and "what’s"."""
    return re.escape(text).replace("'", "['’]?")


def _compile(phrase: str, inputs: dict[str, Input] | None = None) -> re.Pattern:
    names = _PLACEHOLDER.findall(phrase)
    patterns = tuple((inputs or {}).get(n).pattern if (inputs or {}).get(n) else None for n in names)
    return _compile_cached(phrase, tuple(names), patterns)


@lru_cache(maxsize=4096)
def _compile_cached(phrase: str, names: tuple, patterns: tuple) -> re.Pattern:
    by_name = dict(zip(names, patterns))
    parts, pos = [], 0
    p = normalize(phrase)
    for m in _PLACEHOLDER.finditer(p):
        parts += [_lit(p[pos:m.start()]), f"(?P<{m.group(1)}>{by_name.get(m.group(1)) or '.+?'})"]
        pos = m.end()
    parts.append(_lit(p[pos:]))
    return re.compile("^" + "".join(parts) + "$", re.I)


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(normalize(word))}(?!\w)", text) is not None


def _phrase_match(text: str, phrases, inputs: dict[str, Input] | None = None) -> tuple[dict, int] | None:
    best = None
    for ph in phrases:
        m = _compile(ph, inputs).match(text)
        if m:
            score = len(_PLACEHOLDER.sub("", ph))        # more literal words = more specific
            score += 5 * any(inputs and inputs[n].pattern for n in m.groupdict())   # a constrained placeholder beats a free one
            score += 1 * (not m.groupdict())                                         # an exact phrase beats a parametrised one
            if best is None or score > best[1]:
                best = ({k: v.strip() for k, v in m.groupdict().items()}, score)
    return best


# --- canonicalisation: politeness, elongation and typos are removed *before* matching, so tools never see them --------------------
_LEAD = re.compile(r"^(?:(?:please|pls|plz|kindly|hey|hi|hello|yo|ok|okay|rory|can you|could you|would you|will you|can u|could u|"
                   r"can i get|can i have|may i have|i want to|i wanna|i would like to|i'd like to|i need to|i'd love to|let's|lets)[ ,]+)+", re.I)
_TRAIL = re.compile(r"(?:[ ,]+(?:please|pls|plz|thanks|thank you|right now|now|for me|buddy|bro|rory|man|mate|yaar))+$", re.I)
KEYWORD_MAX_WORDS = 3          # a keyword alone is only a request in a short message ("weather", "joke please"), not in a sentence


def strip_wrappers(text: str) -> str:
    """Remove leading/trailing politeness ("could you ... please") without touching the request itself."""
    return _TRAIL.sub("", _LEAD.sub("", text.strip())).strip()


_VOCAB: dict[tuple, frozenset] = {}


def _vocab(specs: list[FeatureSpec]) -> frozenset:
    """Every word the installed tools know (phrases, keywords, examples). Cached per set of installed features."""
    key = tuple(s.full_name for s in specs)
    if key not in _VOCAB:
        words = set()
        for s in specs:
            for src in (*s.phrases, *s.keywords, *s.examples):
                words.update(w for w in re.findall(r"[a-z']+", _PLACEHOLDER.sub(" ", src.lower())) if len(w) >= 2)
        _VOCAB.clear()                                   # only the current registry matters
        _VOCAB[key] = frozenset(words)
    return _VOCAB[key]


def _deelongate(text: str, vocab: frozenset) -> str:
    """hii -> hi, heyyy -> hey, thankss -> thanks (only for words we don't know, and only if the result is a known word)."""
    out = []
    for w in text.split():
        if w.lower() not in vocab and re.search(r"(.)\1", w):
            for squeeze in (re.sub(r"(.)\1{2,}", r"\1\1", w), re.sub(r"(.)\1+", r"\1", w)):
                if squeeze.lower() in vocab:
                    w = squeeze
                    break
        out.append(w)
    return " ".join(out)


def _repair_typos(text: str, vocab: frozenset) -> str:
    """wether -> weather, forcast -> forecast (unknown words of 5+ letters that are very close to a known word)."""
    out = []
    for w in text.split():
        lw = w.lower()
        if len(lw) >= 5 and lw.isalpha() and lw not in vocab:
            if close := difflib.get_close_matches(lw, [v for v in vocab if abs(len(v) - len(lw)) <= 2], n=1, cutoff=0.9):
                w = close[0]
        out.append(w)
    return " ".join(out)


def variants(text: str, specs: list[FeatureSpec]) -> list[str]:
    """The message as typed, cleaned in increasingly aggressive ways; the first variant that matches anything wins."""
    raw = " ".join(text.strip().rstrip(".!?؟ ").split())
    vocab = _vocab(specs)
    stripped = strip_wrappers(raw) or raw
    seen, out = set(), []
    for v in (stripped, raw, _deelongate(stripped, vocab), _repair_typos(_deelongate(stripped, vocab), vocab)):
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def explain(text: str, specs: list[FeatureSpec], original: str = "") -> list[tuple[tuple[int, int], FeatureSpec, dict]]:
    """Every feature that claims the message, best first: [(rank, spec, args)]. Rank is (2, specificity) for a phrase
    match and (1, 0) for a keyword-only match. `decide` takes the first; tests and reports use the whole list to spot ties."""
    t = normalize(text)
    o = normalize(original) if original else t                    # negatives also see the message as typed, before any cleanup
    raw = " ".join(text.strip().rstrip(".!?؟ ").split())        # keeps case, so captured args (URLs, names) stay intact
    found = []
    for spec in specs:
        if any(normalize(n) and (_has_word(t, n) or _has_word(o, n)) for n in spec.negatives):
            continue
        hit = _phrase_match(raw, spec.phrases, spec.inputs)
        if hit:
            found.append(((2, hit[1]), spec, hit[0]))
        elif len(t.split()) <= KEYWORD_MAX_WORDS and any(_has_word(t, k) for k in spec.keywords):
            found.append(((1, 0), spec, {}))
    return sorted(found, key=lambda c: c[0], reverse=True)       # stable: equal ranks keep registry order


def decide(text: str, specs: list[FeatureSpec], last: LastTurn | None = None) -> Decision:
    for v in variants(text, specs):
        ranked = explain(v, specs, text)
        best = ranked[0] if ranked else None
        if best and best[0][0] == 1 and (fu := _followup(v, specs, last)):
            return fu                   # a bare keyword ("link") is weaker than a follow-up to the last answer ("link 2")
        if best:
            _, spec, args = best
            missing = [n for n, i in spec.inputs.items() if i.required and not args.get(n)]
            if missing:
                return Decision("clarify", spec.full_name, args, missing, spec.inputs[missing[0]].ask or f"Which {missing[0]}?")
            return Decision("match", spec.full_name, args)
        if fu := _followup(v, specs, last):
            return fu
    return Decision("none")


def _followup(raw: str, specs: list[FeatureSpec], last: LastTurn | None) -> Decision | None:
    spec = next((s for s in specs if s.full_name == last.feature), None) if last else None
    for fu in spec.followups if spec else ():
        hit = _phrase_match(raw, fu.phrases, spec.inputs)
        if hit:
            args = {**last.args, **{k: v for k, v in hit[0].items() if k in fu.overrides}, **fu.sets}
            return Decision("followup", spec.full_name, args)
    return None
