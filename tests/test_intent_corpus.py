"""Intent detection against the labelled corpus (tests/corpus/intents.py). Failures name the exact message that broke."""
from collections import defaultdict

import pytest

from app.intent.rule_based import decide
from tests.corpus import intents as C
from tests.helpers import real_registry

SPECS = real_registry().specs()
FEATURES = {s.full_name for s in SPECS}
POSITIVE = [*C.PLAIN, *C.NOISY, *C.WRAPPED, *C.PROMOTED, *C.REAL]
ACCURACY_GATE = 0.97


def route(text):
    d = decide(text, SPECS)
    return d.feature if d.kind in ("match", "clarify", "followup") else None


def test_corpus_only_names_real_features():
    named = {f for _, f in POSITIVE if f} | {f for _, f, _ in C.ARGS} | {f for _, f, _ in C.CLARIFY} | {f for _, f, _ in C.GAPS if f}
    assert named <= FEATURES, f"corpus mentions unknown features: {sorted(named - FEATURES)}"


def test_every_answer_feature_is_covered_by_the_corpus():
    """A feature with no corpus line has no regression protection: add one when you add a tool."""
    covered = {f for _, f in POSITIVE} | {f for _, f, _ in C.ARGS}
    uncovered = sorted(s.full_name for s in SPECS if s.full_name not in covered)
    assert not uncovered, f"no corpus message for: {uncovered}"


@pytest.mark.parametrize("text, expected", POSITIVE, ids=[t for t, _ in POSITIVE])
def test_message_routes_to_the_right_feature(text, expected):
    assert route(text) == expected, decide(text, SPECS)


@pytest.mark.parametrize("text, feature, args", C.ARGS, ids=[t for t, _, _ in C.ARGS])
def test_arguments_are_extracted_with_their_case(text, feature, args):
    d = decide(text, SPECS)
    assert d.feature == feature and {k: d.args.get(k) for k in args} == args, d


@pytest.mark.parametrize("text", C.NEGATIVE)
def test_chatter_triggers_no_tool(text):
    assert decide(text, SPECS).kind == "none", decide(text, SPECS)


@pytest.mark.parametrize("text, feature, missing", C.CLARIFY, ids=[t for t, _, _ in C.CLARIFY])
def test_missing_input_asks_a_question(text, feature, missing):
    d = decide(text, SPECS)
    assert (d.kind, d.feature, d.missing[:1]) == ("clarify", feature, [missing]) and d.question.endswith("?") or d.question.endswith(")")


@pytest.mark.parametrize("text, expected, why", C.GAPS, ids=[t for t, _, _ in C.GAPS])
def test_known_gap(text, expected, why, request):
    """Backlog: expected to fail today. When it starts passing, strict xfail turns red: move the line into PLAIN."""
    request.applymarker(pytest.mark.xfail(strict=True, reason=why))
    assert route(text) == expected


def test_per_feature_accuracy_and_zero_false_positives():
    hits, total, wrong = defaultdict(int), defaultdict(int), []
    for text, expected in POSITIVE:
        total[expected] += 1
        if route(text) == expected:
            hits[expected] += 1
        else:
            wrong.append(text)
    low = {f: f"{hits[f]}/{total[f]}" for f in total if hits[f] / total[f] < ACCURACY_GATE}
    assert not low, f"features below {ACCURACY_GATE:.0%}: {low}; misrouted: {wrong}"
    false_positives = [t for t in C.NEGATIVE if route(t)]
    assert not false_positives, f"chatter that triggered a tool: {false_positives}"
