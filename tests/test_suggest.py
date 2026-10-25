"""The synonym suggestion helper (development tool). Logic is tested against a tiny fake WordNet; the real one only if installed."""
import subprocess
import sys
from pathlib import Path

import pytest

from app.nlu.suggest import Sense, paste_block, suggest, tool_words

ROOT = Path(__file__).resolve().parent.parent

# a miniature WordNet: word -> senses (most common first)
FAKE = {
    "joke": [Sense(("joke", "gag", "jest", "jape"), "a humorous anecdote"), Sense(("joke", "gag"), "something amusing")],
    "gag": [Sense(("gag", "joke", "jest"), "a humorous remark"), Sense(("gag", "muzzle"), "restrain speech")],
    "jest": [Sense(("jest", "joke"), "a joke")],
    "jape": [Sense(("jape", "joke"), "a prank")],
    "news": [Sense(("news", "tidings", "word"), "information")],
    "tidings": [Sense(("tidings", "news"), "news")],
    "word": [Sense(("word", "discussion"), "a unit of language"), Sense(("word", "news"), "a message")],   # 'word' means news only as sense 2
    "book": [Sense(("book", "volume"), "a written work"), Sense(("book", "reserve"), "arrange in advance")],
    "volume": [Sense(("volume", "book"), "a book"), Sense(("volume", "loudness"), "sound")],
    "reserve": [Sense(("reserve", "book"), "hold")],
    "fact": [Sense(("fact", "truth"), "a true statement")],
    "truth": [Sense(("truth", "fact", "verity"), "reality")],
    "verity": [Sense(("verity", "truth"), "truth")],
    "Bible": [Sense(("bible",), "x")],
}


def senses(word):
    return FAKE.get(word, [])


def test_tool_words_drop_placeholders_and_function_words():
    assert tool_words(["tell me a joke", "news about {topic}", "what is the weather"]) == ["joke", "news", "weather"]


def test_symmetric_pairs_are_suggested_with_the_reason():
    report = suggest(["joke"], frozenset({"joke"}), {}, senses)
    assert {s.synonym for s in report.suggestions} == {"gag", "jest", "jape"}
    assert all(s.word == "joke" and s.gloss for s in report.suggestions)


def test_wrong_sense_pairs_are_dropped_by_the_symmetry_guard():
    """'word' appears under news, but only as a *second* sense of 'word': a user saying 'word' does not mean news."""
    assert {s.synonym for s in suggest(["news"], frozenset({"news"}), {}, senses).suggestions} == {"tidings"}
    assert "word" in {s.synonym for s in suggest(["news"], frozenset({"news"}), {}, senses, candidate_senses=2).suggestions}      # opt-in noise


def test_book_does_not_suggest_reserve():
    got = {s.synonym for s in suggest(["book"], frozenset({"book"}), {}, senses).suggestions}
    assert "reserve" not in got and "volume" in got


def test_words_some_tool_already_uses_are_not_suggested():
    report = suggest(["joke"], frozenset({"joke", "gag"}), {}, senses)
    assert "gag" not in {s.synonym for s in report.suggestions} and report.skipped_known >= 1


def test_existing_synonyms_are_not_suggested_again():
    assert "jest" not in {s.synonym for s in suggest(["joke"], frozenset({"joke"}), {"jest": "joke"}, senses).suggestions}


def test_a_candidate_pointing_at_two_tool_words_is_reported_not_suggested():
    fake = {**FAKE, "fact": [Sense(("fact", "truth"), "")], "joke": [Sense(("joke", "truth"), "")], "truth": [Sense(("truth", "fact", "joke"), "")]}
    report = suggest(["fact", "joke"], frozenset({"fact", "joke"}), {}, lambda w: fake.get(w, []))
    assert report.ambiguous == {"truth": ["fact", "joke"]} and report.suggestions == []


def test_only_plain_lowercase_single_words_survive():
    fake = {"joke": [Sense(("joke", "Gag", "wise_crack", "jo", "j0ke"), "")], "gag": [Sense(("joke",), "")]}
    assert suggest(["joke"], frozenset({"joke"}), {}, lambda w: fake.get(w, [])).suggestions == []


def test_looser_settings_find_more_and_the_default_is_the_strict_one():
    strict = {s.synonym for s in suggest(["book"], frozenset({"book"}), {}, senses).suggestions}
    loose = {s.synonym for s in suggest(["book"], frozenset({"book"}), {}, senses, word_senses=2, candidate_senses=2).suggestions}
    assert strict == {"volume"} and loose == {"volume", "reserve"} and strict < loose


def test_paste_block_is_valid_python():
    block = paste_block(suggest(["joke"], frozenset({"joke"}), {}, senses).suggestions)
    assert eval(block.removeprefix("synonyms=")) == {"gag": "joke", "jape": "joke", "jest": "joke"}
    assert paste_block([]).startswith("#")


# --- the real thing, only when WordNet is installed -------------------------------------------------------------------------
def wordnet_ready():
    try:
        import nltk
        nltk.data.path.insert(0, str(ROOT / "data" / "nltk_data"))
        from nltk.corpus import wordnet
        wordnet.ensure_loaded()
        return True
    except Exception:                                    # noqa: BLE001 - not installed / data not downloaded
        return False


@pytest.mark.skipif(not wordnet_ready(), reason="WordNet not installed (pip install nltk; scripts/suggest_synonyms.py --download)")
def test_cli_suggests_for_given_words():
    out = subprocess.run([sys.executable, "scripts/suggest_synonyms.py", "--words", "begin", "big"], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    assert "== (given words)   (2 words checked)" in out.stdout and "review first" in out.stdout
    assert "synonyms={" in out.stdout or "no safe suggestions" in out.stdout


@pytest.mark.skipif(not wordnet_ready(), reason="WordNet not installed")
def test_cli_rejects_an_unknown_tool():
    out = subprocess.run([sys.executable, "scripts/suggest_synonyms.py", "nope"], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode != 0 and "unknown tool" in (out.stdout + out.stderr)
