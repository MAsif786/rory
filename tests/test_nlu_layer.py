"""The NLU layer: entity pre-pass (dates, spoken maths) and synonyms. Both may widen what Rory understands; neither may invent an intent."""
from datetime import date

import pytest

from app.core.registry import Registry
from app.core.tool import Tool
from app.intent.rule_based import _vocab, decide
from app.nlu.entities import DATE_WORDS, days_ahead, describe, extract_dates, spoken_maths, words_to_numbers
from app.nlu.lexicon import CORE, lexicon, mentions_synonym, rewrite
from tests.corpus import intents as C
from tests.helpers import real_registry

SPECS = real_registry().specs()
SUN = date(2026, 10, 25)          # a Sunday: makes weekday arithmetic checkable by hand


# --- dates ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, clean, when", [
    ("weather next monday in karachi", "weather in karachi", "next monday"), ("weather on friday in murree", "weather in murree", "friday"),
    ("forecast for the weekend in dubai", "forecast in dubai", "weekend"), ("weather tomorrow", "weather", "tomorrow"),
    ("will it rain the day after tomorrow in london", "will it rain in london", "day after tomorrow"),
    ("weather in 3 days in paris", "weather in paris", "in 3 days"), ("weather 5 days from now in paris", "weather in paris", "in 5 days"),
    ("weather next week in rome", "weather in rome", "next week"), ("weather tonight in oslo", "weather in oslo", "tonight"),
    ("kal ka mausam lahore", "ka mausam lahore", "tomorrow"), ("parson ka mausam lahore", "ka mausam lahore", "day after tomorrow"),
    ("lahore ka mausam aaj", "lahore ka mausam", "today")])
def test_dates_are_lifted_out(text, clean, when):
    assert extract_dates(text) == (clean, {"when": when})


@pytest.mark.parametrize("text", ["weather in lahore", "100 usd to pkr", "play hangman", "who is einstein"])
def test_text_without_a_date_is_untouched(text):
    assert extract_dates(text) == (text, {})


def test_a_weekday_word_is_only_trusted_as_a_date_by_features_that_take_one():
    assert extract_dates("the monday blues")[1] == {"when": "monday"}                      # the extractor is deliberately simple ...
    assert decide("the monday blues", SPECS).via != "date"                                  # ... the engine only acts on it for a `when` feature


@pytest.mark.parametrize("label, ahead, said", [
    ("today", 0, "today"), ("tomorrow", 1, "tomorrow"), ("day after tomorrow", 2, "Tuesday 27 Oct"), ("monday", 1, "tomorrow"),
    ("friday", 5, "Friday 30 Oct"), ("next sunday", 7, "Sunday 01 Nov"), ("sunday", 0, "today"), ("weekend", 0, "today"),
    ("in 3 days", 3, "Wednesday 28 Oct"), ("next week", 7, "Sunday 01 Nov"), ("someday", None, "today")])
def test_days_ahead_and_wording(label, ahead, said):
    assert days_ahead(label, SUN) == ahead and describe(label, SUN) == said


def test_weekend_counts_from_a_weekday():
    assert days_ahead("weekend", date(2026, 10, 21)) == 3          # Wednesday -> Saturday


def test_date_words_are_a_pattern_tools_can_reuse():
    import re
    for ok in ("tomorrow", "next monday", "weekend", "in 3 days", "friday"):
        assert re.fullmatch(DATE_WORDS, ok), ok


def test_a_date_never_ends_up_inside_a_place_slot():
    for text in ("weather next monday in karachi", "forecast for the weekend in dubai", "weather tomorrow in karachi", "weather in 3 days in paris"):
        d = decide(text, SPECS)
        assert d.via == "date" and not any(w in d.args["place"] for w in ("next", "weekend", "tomorrow", "days")), d
        assert d.args["when"]


def test_dates_only_apply_to_features_that_take_a_when_input():
    assert decide("today's news", SPECS).feature == "news.headlines" and decide("news today", SPECS).feature == "news.headlines"
    assert decide("good morning", SPECS).feature == "greetings.daypart"
    assert decide("tell me about tomorrow", SPECS).feature == "wiki.lookup"        # not rewritten: wiki has no `when`


def test_missing_place_keeps_the_date_while_asking():
    d = decide("weather tomorrow", SPECS)
    assert (d.kind, d.missing, d.args["when"]) == ("clarify", ["place"], "tomorrow")


# --- spoken maths -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("fifteen", "15"), ("twenty five", "25"), ("one hundred and five", "105"), ("two thousand three hundred", "2300"), ("a hundred", "a 100"),
    ("what's fifteen plus four", "what's 15 + 4"), ("square root of 144", "sqrt(144)"), ("twenty five times four", "25 * 4"),
    ("20 divided by 4", "20 / 4"), ("two to the power of ten", "2 ** 10"), ("9 squared", "9**2"), ("10 minus 3", "10 - 3"),
    ("weather in lahore", "weather in lahore"), ("no one knows", "no 1 knows")])
def test_spoken_maths(text, expected):
    assert spoken_maths(text) == expected


@pytest.mark.parametrize("text, feature", [("what's fifteen plus four", "calc.calc"), ("square root of 144", "calc.calc"),
                                           ("twenty percent of fifty", "calc.percent"), ("what is nine times nine", "calc.calc")])
def test_spoken_maths_reaches_the_calculator(text, feature):
    d = decide(text, SPECS)
    assert d.feature == feature and d.via == "maths"


@pytest.mark.parametrize("text", ["no one knows", "one love", "i want two tickets", "give me ten minutes", "three little pigs", "the sixth sense",
                                  "i am twenty years old", "call me at five"])
def test_number_words_in_ordinary_sentences_do_not_become_maths(text):
    d = decide(text, SPECS)
    assert d.via != "maths" and d.feature != "calc.calc"


# --- synonyms ---------------------------------------------------------------------------------------------------------------
def test_core_and_tool_synonyms_are_merged():
    table = lexicon(SPECS)
    assert table["temp"] == "temperature" and table["gag"] == "joke" and table["tidings"] == "news" and table["farewell"] == "bye"
    assert set(CORE) <= set(table)


@pytest.mark.parametrize("text, feature, via", [
    ("tell me a jest", "fun.joke", "synonym"), ("any tidings today", "news.headlines", "synonym"), ("farewell", "greetings.bye", "synonym"),
    ("what's the climate in lahore", "weather.current", "synonym"), ("temp in lahore", "weather.current", "synonym"),
    ("who is the writer of dune", "book.info", "synonym"), ("exchange 100 dollars to rupees", "currency.convert", "synonym"),
    ("gratitude", "greetings.thanks", "synonym"), ("a nation fact: japan", None, None)])
def test_synonyms_widen_understanding(text, feature, via):
    d = decide(text, SPECS)
    if feature:
        assert (d.feature, d.via) == (feature, via), d


def test_a_synonym_beats_a_weaker_direct_match():
    """'who is the writer of dune' matches Wikipedia directly, but the book tool's 'author of' phrase is clearly more specific."""
    assert decide("who is the writer of dune", SPECS).feature == "book.info"


def test_synonyms_never_rewrite_words_the_tools_already_know():
    known = _vocab(SPECS)
    shadowed = sorted(k for k in lexicon(SPECS) if k in known)
    assert not shadowed, f"these synonyms are also words some phrase uses, so they would never apply: {shadowed}"
    assert rewrite("book 1984", {"book": "novel"}, frozenset({"book"})) == ("book 1984", [])


def test_rewrites_are_limited_to_two_words():
    new, changed = rewrite("a b c d", {"a": "x", "b": "y", "c": "z"}, frozenset())
    assert len(changed) == 2 and new == "x y c d"


def test_mentions_synonym_is_cheap_and_exact():
    t, k = lexicon(SPECS), _vocab(SPECS)
    assert mentions_synonym("tell me a jest", t, k) and not mentions_synonym("tell me a joke", t, k)


OUT_OF_SCOPE = ["book a flight to dubai", "what is your favourite colour", "order me a pizza", "call my mother", "turn on the lights", "set an alarm for 7",
                "play some music", "send an email to ali", "i need a loan", "fix my laptop", "where can i buy shoes", "translate this to french",
                "open the door", "book me a taxi", "write a poem", "what is the meaning of life"]


@pytest.mark.parametrize("text", [*C.NEGATIVE, *OUT_OF_SCOPE])
def test_synonyms_never_turn_chatter_or_out_of_scope_requests_into_tool_calls(text):
    d = decide(text, SPECS)
    assert d.via != "synonym", f"{text!r} was rewritten into {d.feature}"


# --- registry validation of tool synonyms -----------------------------------------------------------------------------------
def tool_with(name, phrase, **synonyms):
    t = Tool(name, synonyms=synonyms)

    @t.feature("go", phrases=[phrase], examples=[phrase])
    async def go(ctx): ...
    return t


@pytest.mark.parametrize("synonyms, why", [
    ({"gag": "joke"}, None), ({"two words": "joke"}, "single lowercase words"), ({"x": "joke"}, "single lowercase words"),
    ({"joke": "joke"}, "maps to itself"), ({"gag": "pun"}, "does not appear in any phrase"), ({"temp": "heat"}, "does not appear")])
def test_registry_checks_tool_synonyms(synonyms, why):
    reg = Registry()
    reg.add(tool_with("jokes", "tell me a joke", **synonyms), "jokes")
    assert ("jokes" in reg.tools) == (why is None), reg.rejected
    if why:
        assert why in reg.rejected["jokes"]


def test_two_tools_cannot_disagree_about_a_synonym():
    reg = Registry()
    reg.add(tool_with("a", "tell me a joke", gag="joke"), "a")
    reg.add(tool_with("b", "tell me a fact", gag="fact"), "b")
    assert "a" in reg.tools and "contradicts" in reg.rejected["b"]
    reg.add(tool_with("c", "tell me a joke now", gag="joke"), "c")          # agreeing is fine
    assert "c" in reg.tools


def test_a_tool_cannot_redefine_a_core_abbreviation():
    reg = Registry()
    reg.add(tool_with("t", "hello there", temp="hello"), "t")
    assert "contradicts" in reg.rejected["t"]


# --- things found by probing real-looking messages --------------------------------------------------------------------------
@pytest.mark.parametrize("text, feature, place", [("what is the temp in dubai", "weather.current", "dubai"), ("what's the temperature in oslo", "weather.current", "oslo"),
                                                  ("temp in lahore", "weather.current", "lahore")])
def test_temperature_questions_reach_weather(text, feature, place):
    d = decide(text, SPECS)
    assert (d.feature, d.args["place"]) == (feature, place)


@pytest.mark.parametrize("text", ["list of jokes or facts", "any country facts", "best country facts", "my country facts"])
def test_the_country_slot_does_not_swallow_requests(text):
    assert decide(text, SPECS).feature != "country.facts"


@pytest.mark.parametrize("text, country", [("capital of Sri Lanka", "Sri Lanka"), ("capital of Bosnia and Herzegovina", "Bosnia and Herzegovina"),
                                           ("population of the Netherlands", "the Netherlands"), ("capital of Cote d'Ivoire", "Cote d'Ivoire")])
def test_real_country_names_still_work(text, country):
    assert decide(text, SPECS).args["country"].lower() == country.lower()


def test_the_tool_template_is_a_valid_tool():
    """The template is what authors copy: it must load cleanly (synonyms, patterns, examples included)."""
    from tools._template.tool import tool
    reg = Registry()
    reg.add(tool, "template")
    assert "template" in reg.tools, reg.rejected
    assert decide("greet sara", reg.specs()).args == {"name": "sara"}
