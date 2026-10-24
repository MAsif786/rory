"""Routing quality across every installed tool: examples hit their own feature, negatives never do, chatter matches nothing."""
import pytest

from app.core.registry import Registry
from app.intent.rule_based import decide

REGISTRY = Registry().discover()
SPECS = REGISTRY.specs()
EXAMPLES = [(s.full_name, ex) for s in SPECS for ex in s.examples]
NEGATIVES = [(s.full_name, n) for s in SPECS for n in s.negatives]

CHATTER = [
    "ok", "lol", "tell me a story", "whether or not to go", "i am so tired today",
    "book a flight to dubai", "i want to book a table", "movie night at my place", "bed time", "what time to eat",
    "let's meet at 5", "my phone number is 555-1234", "yes/no", "and/or", "can you help me with my homework",
    "see you tomorrow", "what do you think", "i'll roll up my sleeves", "lets play",
]


def test_nothing_rejected():
    assert REGISTRY.rejected == {}


def test_every_tool_has_metadata_for_help():
    assert all(t.title and t.description for t in REGISTRY.tools.values())


@pytest.mark.parametrize("feature, example", EXAMPLES)
def test_example_routes_to_its_own_feature(feature, example):
    d = decide(example, SPECS)
    assert d.kind in ("match", "clarify") and d.feature == feature, f"{example!r} -> {d}"


@pytest.mark.parametrize("feature, negative", NEGATIVES)
def test_negative_never_matches_its_feature(feature, negative):
    assert decide(negative, SPECS).feature != feature


@pytest.mark.parametrize("text", CHATTER)
def test_chatter_matches_nothing(text):
    d = decide(text, SPECS)
    assert d.kind == "none", f"{text!r} -> {d}"
