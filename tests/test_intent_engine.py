"""The rule-based engine itself: canonicalisation, scoring, ties, and its worst-case speed."""
import re
import time

import pytest

from app.core.schemas import Followup, Input
from app.core.tool import Tool
from app.intent.decision import LastTurn
from app.intent.rule_based import decide, explain, strip_wrappers, variants
from tests.helpers import real_registry

SPECS = real_registry().specs()

# values to fill each {placeholder} with when generating a message from a phrase
SAMPLES = {"place": "lahore", "amount": "100", "base": "usd", "quote": "pkr", "value": "5", "src": "km", "dst": "miles", "expr": "2+2", "pct": "15",
           "n": "200", "ref": "2:255", "lang": "urdu", "kw": "patience", "name": "rahman", "book": "jalalayn", "topic": "volcanoes", "title": "inception",
           "country": "japan", "query": "fastapi", "repo": "psf/requests", "ip": "8.8.8.8", "url": "https://example.com", "section": "tech",
           "part": "morning", "mood": "tired", "when": "tomorrow", "dice": "2d6", "options": "pizza or sushi", "pick": "2"}


def fill(phrase: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: SAMPLES.get(m.group(1), "test"), phrase)


ALL_PHRASES = [(s.full_name, ph) for s in SPECS for ph in s.phrases]


# --- canonicalisation ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("please flip a coin", "flip a coin"), ("could you convert 100 usd to pkr please", "convert 100 usd to pkr"),
    ("hey, can you tell me a joke", "tell me a joke"), ("i want to play hangman", "play hangman"), ("weather in lahore right now", "weather in lahore"),
    ("hello", "hello"), ("thanks", "thanks"), ("weather in lahore", "weather in lahore")])
def test_politeness_is_stripped_but_not_the_request(text, expected):
    assert strip_wrappers(text) == expected


def test_greetings_are_not_stripped_to_nothing():
    assert variants("hello", SPECS)[0] == "hello"                      # an empty stripped message falls back to the original


def test_variants_start_with_the_cleanest_and_keep_the_original():
    v = variants("Please flip a coin!", SPECS)
    assert v[0] == "flip a coin" and "Please flip a coin" in v


@pytest.mark.parametrize("typo, fixed", [("wether in lahore", "weather"), ("forcast for tokyo", "forecast"), ("temprature in dubai", "temperature"),
                                         ("heyyy", "hey"), ("hii", "hi")])
def test_typos_and_elongation_are_repaired(typo, fixed):
    assert any(fixed in v for v in variants(typo, SPECS))


@pytest.mark.parametrize("text", ["whether or not to go", "i went to the zone", "the quick brown fox"])
def test_real_words_are_not_mangled_into_commands(text):
    assert decide(text, SPECS).kind == "none"


def test_apostrophes_are_optional():
    for text in ("whats the weather in lahore", "what's the weather in lahore", "what’s the weather in lahore"):
        assert decide(text, SPECS).feature == "weather.current", text


def test_negatives_see_the_original_message_not_only_the_cleaned_one():
    # "whether or not" is a negative of weather; typo repair must not be able to sneak the message past it
    assert decide("whether or not to go", SPECS).kind == "none"


# --- keyword-only matches ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["the weather was terrible last week", "that joke was bad", "i watched a movie yesterday", "the news was boring"])
def test_a_keyword_inside_a_sentence_is_not_a_request(text):
    assert decide(text, SPECS).kind == "none"


@pytest.mark.parametrize("text, feature", [("weather", "weather.current"), ("joke", "fun.joke"), ("tafsir", "quran.tafsir"), ("google", "search.web")])
def test_a_lone_keyword_is_a_request(text, feature):
    assert decide(text, SPECS).feature == feature


def test_a_followup_beats_a_bare_keyword_but_not_a_full_phrase():
    t = Tool("feed")

    @t.feature("list", phrases=["list"], keywords=["link"], examples=["list"], inputs={"pick": Input(type="int", pattern="[1-9]")},
               followups=[Followup(phrases=["link {pick}"], overrides=["pick"])])
    async def list_(ctx, pick): ...

    @t.feature("other", phrases=["link 7 exactly"], examples=["link 7 exactly"])
    async def other(ctx): ...

    specs = [f.spec for f in t.features.values()]
    last = LastTurn("feed.list", {"pick": None})
    assert decide("link 2", specs, last).kind == "followup"
    assert decide("link 7 exactly", specs, last).feature == "feed.other"      # a real phrase match is not overridden


# --- phrase-level consistency ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("feature, phrase", ALL_PHRASES, ids=[f"{f}:{p}" for f, p in ALL_PHRASES])
def test_every_phrase_routes_to_its_own_feature(feature, phrase):
    """Fills each declared phrase with a sample value and checks the engine agrees which feature owns it (catches collisions)."""
    d = decide(fill(phrase), SPECS)
    assert d.feature == feature, f"{fill(phrase)!r} routed to {d.feature}, declared by {feature}"


def test_no_two_features_tie_on_any_declared_phrase_or_example():
    """An exact tie is resolved by registry order: it works today but breaks silently when a tool is added or renamed."""
    ties = []
    for s in SPECS:
        for src in (*s.phrases, *s.examples):
            ranked = explain(fill(src), SPECS)
            if len(ranked) > 1 and ranked[0][0] == ranked[1][0] and ranked[0][1].full_name != ranked[1][1].full_name:
                ties.append((fill(src), ranked[0][1].full_name, ranked[1][1].full_name))
    assert not ties, f"order-dependent ties: {ties}"


# --- speed & robustness ------------------------------------------------------------------------------------------------------------
ADVERSARIAL = ["a" * 5000, "weather in " + "a" * 5000, "1+" * 2000, "(" * 3000, "convert " + "9" * 3000 + " usd to pkr", " ".join(["the"] * 1500),
               "who is " + "very " * 1000 + "tall", "https://" + "a." * 1500 + "com", "🙂" * 3000, "\n".join(["weather in lahore"] * 300),
               "{place}" * 500, ".*" * 1500, "news about " + "x" * 2000 + " the"]


@pytest.mark.parametrize("text", ADVERSARIAL, ids=[f"adversarial-{i}" for i in range(len(ADVERSARIAL))])
def test_adversarial_input_is_decided_quickly(text):
    """Patterns are regexes built from tool authors' input: a bad one can hang the bot on a crafted message (ReDoS)."""
    start = time.perf_counter()
    decide(text, SPECS)
    assert time.perf_counter() - start < 0.5, "engine took too long on adversarial input"


def test_typical_messages_are_decided_in_milliseconds():
    decide("warm up", SPECS)
    start = time.perf_counter()
    for text in ("weather in lahore", "100 usd to pkr", "blah blah blah blah", "who is albert einstein", "wether in lahor"):
        decide(text, SPECS)
    assert (time.perf_counter() - start) / 5 < 0.05
