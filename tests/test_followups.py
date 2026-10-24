"""Follow-ups, derived from each tool's own metadata so a new tool's follow-ups are tested the day it is added.

For every Followup a tool declares, every phrase is filled with sample values and replayed after the feature's own example.
The follow-up must (1) stay on the same feature, (2) change exactly the arguments it declares, (3) keep all the others,
and (4) never fire without context."""
import pytest

from app.intent.decision import LastTurn
from app.intent.rule_based import decide
from tests.helpers import real_registry
from tests.test_intent_engine import fill

SPECS = real_registry().specs()
CASES = [(s.full_name, fu_i, ph) for s in SPECS for fu_i, fu in enumerate(s.followups) for ph in fu.phrases]
BY_NAME = {s.full_name: s for s in SPECS}


def baseline_args(spec):
    """The arguments the feature's first example produced: what a user would have 'just asked'."""
    d = decide(spec.examples[0], SPECS)
    assert d.feature == spec.full_name, f"{spec.full_name}: its first example routes to {d.feature}"
    return {k: (v if v is not None else spec.inputs[k].default) for k, v in {**{n: None for n in spec.inputs}, **d.args}.items()}


@pytest.mark.parametrize("feature, index, phrase", CASES, ids=[f"{f}#{i}:{p}" for f, i, p in CASES])
def test_followup_changes_only_what_it_declares(feature, index, phrase):
    spec = BY_NAME[feature]
    fu = spec.followups[index]
    last = baseline_args(spec)
    text = fill(phrase)
    d = decide(text, SPECS, LastTurn(feature, last))
    assert d.feature == feature, f"{text!r} after {spec.examples[0]!r} routed to {d.feature} ({d.kind})"
    assert d.kind in ("followup", "match", "clarify"), d
    for name in fu.overrides:
        assert d.args.get(name) not in (None, ""), f"{text!r}: override {name!r} was not filled: {d.args}"
    for name, value in fu.sets.items():
        assert d.args.get(name) == value, f"{text!r}: expected {name}={value!r}, got {d.args}"
    if d.kind == "followup":
        untouched = {k: v for k, v in last.items() if k not in fu.overrides and k not in fu.sets}
        assert {k: d.args.get(k) for k in untouched} == untouched, f"{text!r} changed arguments it should have kept: {d.args} vs {last}"


@pytest.mark.parametrize("feature, index, phrase", CASES, ids=[f"{f}#{i}:{p}" for f, i, p in CASES])
def test_followup_does_nothing_without_context(feature, index, phrase):
    d = decide(fill(phrase), SPECS, None)
    assert d.kind != "followup"


def test_followups_only_exist_on_features_that_can_be_repeated():
    """A follow-up on a game-start or a greeting makes no sense; catch it if one is added by mistake."""
    odd = [s.full_name for s in SPECS if s.followups and s.kind == "session"]
    assert not odd, odd


def test_a_followup_phrase_never_hijacks_a_fresh_request_of_another_tool():
    """'what about X' is a follow-up only when the last answer allows it. After weather, 'what about 5 km in miles' is units."""
    last = LastTurn("weather.current", {"place": "Lahore", "day": None})
    assert decide("5 km in miles", SPECS, last).feature == "units.convert"
    assert decide("who is einstein", SPECS, last).feature == "wiki.lookup"
