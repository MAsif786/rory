"""Rule-based engine: matches messages against the phrases/keywords/negatives/followups tools declare."""
import re

from app.core.schemas import FeatureSpec, Input
from app.intent.decision import Decision, LastTurn

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def normalize(text: str) -> str:
    return " ".join(text.lower().strip().rstrip(".!?؟ ").split())


def _compile(phrase: str, inputs: dict[str, Input] | None = None) -> re.Pattern:
    parts, pos = [], 0
    p = normalize(phrase)
    for m in _PLACEHOLDER.finditer(p):
        spec = (inputs or {}).get(m.group(1))
        parts += [re.escape(p[pos:m.start()]), f"(?P<{m.group(1)}>{spec.pattern if spec and spec.pattern else '.+?'})"]
        pos = m.end()
    parts.append(re.escape(p[pos:]))
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
            if best is None or score > best[1]:
                best = ({k: v.strip() for k, v in m.groupdict().items()}, score)
    return best


def decide(text: str, specs: list[FeatureSpec], last: LastTurn | None = None) -> Decision:
    t = normalize(text)
    raw = " ".join(text.strip().rstrip(".!?؟ ").split())        # keeps case, so captured args (URLs, names) stay intact
    best: tuple[int, FeatureSpec, dict] | None = None
    for spec in specs:
        if any(normalize(n) and _has_word(t, n) for n in spec.negatives):
            continue
        hit = _phrase_match(raw, spec.phrases, spec.inputs)
        if hit:
            rank = (2, hit[1])
            args = hit[0]
        elif any(_has_word(t, k) for k in spec.keywords):
            rank, args = (1, 0), {}
        else:
            continue
        if best is None or rank > best[0]:
            best = (rank, spec, args)
    if best and best[0][0] == 1 and (fu := _followup(raw, specs, last)):
        return fu                       # a bare keyword ("link") is weaker than a follow-up to the last answer ("link 2")
    if best:
        _, spec, args = best
        missing = [n for n, i in spec.inputs.items() if i.required and not args.get(n)]
        if missing:
            return Decision("clarify", spec.full_name, args, missing, spec.inputs[missing[0]].ask or f"Which {missing[0]}?")
        return Decision("match", spec.full_name, args)
    return _followup(raw, specs, last) or Decision("none")


def _followup(raw: str, specs: list[FeatureSpec], last: LastTurn | None) -> Decision | None:
    spec = next((s for s in specs if s.full_name == last.feature), None) if last else None
    for fu in spec.followups if spec else ():
        hit = _phrase_match(raw, fu.phrases, spec.inputs)
        if hit:
            args = {**last.args, **{k: v for k, v in hit[0].items() if k in fu.overrides}, **fu.sets}
            return Decision("followup", spec.full_name, args)
    return None
