"""Rule-based engine: matches messages against the phrases/keywords/negatives/followups tools declare."""
import re

from app.core.schemas import FeatureSpec
from app.intent.decision import Decision, LastTurn

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def normalize(text: str) -> str:
    return " ".join(text.lower().strip().rstrip(".!?؟ ").split())


def _compile(phrase: str) -> re.Pattern:
    parts, pos = [], 0
    p = normalize(phrase)
    for m in _PLACEHOLDER.finditer(p):
        parts += [re.escape(p[pos:m.start()]), f"(?P<{m.group(1)}>.+?)"]
        pos = m.end()
    parts.append(re.escape(p[pos:]))
    return re.compile("^" + "".join(parts) + "$")


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(normalize(word))}(?!\w)", text) is not None


def _phrase_match(text: str, phrases) -> tuple[dict, int] | None:
    best = None
    for ph in phrases:
        m = _compile(ph).match(text)
        if m:
            score = len(_PLACEHOLDER.sub("", ph))        # more literal words = more specific
            if best is None or score > best[1]:
                best = ({k: v.strip() for k, v in m.groupdict().items()}, score)
    return best


def decide(text: str, specs: list[FeatureSpec], last: LastTurn | None = None) -> Decision:
    t = normalize(text)
    best: tuple[int, FeatureSpec, dict] | None = None
    for spec in specs:
        if any(normalize(n) and normalize(n) in t for n in spec.negatives):
            continue
        hit = _phrase_match(t, spec.phrases)
        if hit:
            rank = (2, hit[1])
            args = hit[0]
        elif any(_has_word(t, k) for k in spec.keywords):
            rank, args = (1, 0), {}
        else:
            continue
        if best is None or rank > best[0]:
            best = (rank, spec, args)
    if best:
        _, spec, args = best
        missing = [n for n, i in spec.inputs.items() if i.required and not args.get(n)]
        if missing:
            return Decision("clarify", spec.full_name, args, missing, f"Which {missing[0]}?")
        return Decision("match", spec.full_name, args)

    if last:
        spec = next((s for s in specs if s.full_name == last.feature), None)
        for fu in spec.followups if spec else ():
            hit = _phrase_match(t, fu.phrases)
            if hit:
                args = {**last.args, **{k: v for k, v in hit[0].items() if k in fu.overrides}, **fu.sets}
                return Decision("followup", spec.full_name, args)
    return Decision("none")
