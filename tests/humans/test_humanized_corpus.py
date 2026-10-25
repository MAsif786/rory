"""Real people do not type like test fixtures. Every message of the corpus is retyped the way people mistype it (typos, autocorrect damage,
shouting, filler, emoji, missing punctuation) with a fixed seed, and the engine must still pick the same tool.

The floors below are measured, not hoped for: raise them when the engine improves, never lower one to make a failure go away.
A failing assertion prints the worst offenders, so the fix starts from real examples."""
import random
from collections import defaultdict

import pytest

from app.intent.rule_based import decide
from tests.corpus import intents as C
from tests.helpers import real_registry
from tests.humans import humanizer as H

SPECS = real_registry().specs()
POSITIVE = [*C.PLAIN, *C.NOISY, *C.WRAPPED, *C.PROMOTED, *C.REAL]
SEED = 2026

# noise -> minimum share of messages still understood
FLOORS = {"lower": 1.0, "upper": 1.0, "title": 1.0, "no_punctuation": 1.0, "extra_punctuation": 1.0, "no_apostrophes": 1.0, "double_spaces": 1.0, "emoji": 1.0,
          "filler_before": 0.96, "filler_after": 0.85,
          "duplicate": 0.80, "elongate": 0.78, "neighbour": 0.78, "swap": 0.76, "drop": 0.68}


def _feature(text: str):
    d = decide(text, SPECS)
    return d.feature if d.kind != "none" else None


def _score(noise: str, per: int = 2):
    rng, ok, total, bad = random.Random(f"{SEED}-{noise}"), 0, 0, []
    for text, expected in POSITIVE:
        for messy, _ in H.variants(text, rng, per, only=[noise]):
            total += 1
            got = _feature(messy)
            if got == expected:
                ok += 1
            else:
                bad.append(f"{messy!r} (from {text!r}): expected {expected}, got {got}")
    return ok / total, bad


@pytest.mark.parametrize("noise", list(FLOORS))
def test_a_kind_of_mess_is_still_understood(noise):
    share, bad = _score(noise)
    assert share >= FLOORS[noise], f"{noise}: {share:.1%} understood, floor {FLOORS[noise]:.0%}. Examples:\n  " + "\n  ".join(bad[:12])


def test_two_kinds_of_mess_at_once():
    rng, ok, total, bad = random.Random(SEED), 0, 0, []
    for text, expected in POSITIVE:
        for messy, used in H.variants(text, rng, 8):
            if len(used) < 2:
                continue
            total += 1
            got = _feature(messy)
            ok += got == expected
            if got != expected:
                bad.append(f"{used} {messy!r}: expected {expected}, got {got}")
    assert ok / total >= 0.82, f"{ok / total:.1%} of double-mess messages understood. Examples:\n  " + "\n  ".join(bad[:12])


def test_a_typo_never_turns_chatter_into_a_command():
    """The cost of over-eager repair: 'movie nigth at my place' must not look up a movie, 'one moer time' must not tell the time."""
    rng, hits = random.Random(SEED), []
    for text in C.NEGATIVE:
        for messy, used in H.variants(text, rng, 12):
            if (got := _feature(messy)):
                hits.append(f"{messy!r} (from {text!r}) -> {got}")
    assert not hits, f"{len(hits)} chatter messages now trigger a tool:\n  " + "\n  ".join(hits[:15])


def test_a_typo_in_a_place_name_is_not_corrected():
    """Arguments belong to the user: a misspelt or unknown city is passed on exactly as typed."""
    for typed in ["Lahor", "Karchi", "Islamabd", "Rawalpindii", "Faisalabd", "Hyderbad"]:
        d = decide(f"weather in {typed}", SPECS)
        assert d.feature == "weather.current" and d.args["place"] == typed, (typed, d)
    d = decide("wether in Lahor", SPECS)
    assert d.feature == "weather.current" and d.args["place"] == "Lahor", d


def test_real_words_are_not_rewritten_into_commands():
    for text in ["whether it rains is not my problem", "i play guitar on weekends", "the weather was awful yesterday", "whether or not to go"]:
        assert _feature(text) is None, text
