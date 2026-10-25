"""Synonyms, derived from the data: nothing here names a specific synonym, so a synonym added to any tool tomorrow is tested tomorrow.

For every (synonym -> target) pair in the lexicon, take every declared phrase that contains the target word, swap in the synonym, fill the
placeholders, and require the engine to read the new message as the same intent with the same arguments as the original. That proves the
synonym works in real sentence shapes (not only the one example its author tried) and cannot change what a message means."""
import re

import pytest

from app.intent.rule_based import decide
from app.nlu.lexicon import CORE, lexicon
from tests.helpers import real_registry
from tests.test_intent_engine import fill

SPECS = real_registry().specs()
TABLE = lexicon(SPECS)
TOOL_SYNONYMS = {k: v for k, v in TABLE.items() if k not in CORE}
CASES = []
for syn, target in TABLE.items():
    for spec in SPECS:
        for phrase in spec.phrases:
            if any(re.search(rf"(?<![\w{{']){re.escape(abbr)}(?![\w}}'])", phrase.lower()) for abbr in CORE):
                continue                                        # chat abbreviations ("thanks u"): swapping a second word makes nonsense, not a test
            if re.search(rf"(?<![\w{{']){re.escape(target)}(?![\w}}'])", phrase.lower()):
                CASES.append((syn, target, spec.full_name, phrase))


def swap(phrase: str, target: str, syn: str) -> str:
    return re.sub(rf"(?<![\w{{']){re.escape(target)}(?![\w}}'])", syn, phrase, flags=re.I)


# messages that matched directly but that a stronger synonym reading deliberately takes over ('writer' -> 'author' makes the book tool the better answer)
DELIBERATE_UPGRADES = {"who is the writer of dune"}


def test_there_are_synonyms_to_test():
    assert len(TOOL_SYNONYMS) >= 15 and len(CASES) >= 100


@pytest.mark.parametrize("syn, target, feature, phrase", CASES, ids=[f"{s}->{t}|{f}|{p}" for s, t, f, p in CASES])
def test_a_synonym_means_the_same_as_its_target_in_every_phrase_that_uses_it(syn, target, feature, phrase):
    original = decide(fill(phrase), SPECS)
    if original.feature != feature or original.kind not in ("match", "clarify"):
        pytest.skip("the original phrase is itself outranked by another feature; nothing to compare")
    swapped = decide(fill(swap(phrase, target, syn)), SPECS)
    assert (swapped.feature, swapped.kind, swapped.args) == (original.feature, original.kind, original.args), (
        f"{fill(swap(phrase, target, syn))!r} -> {swapped}\n  but {fill(phrase)!r} -> {original}")


@pytest.mark.parametrize("syn, target", sorted(TOOL_SYNONYMS.items()))
def test_every_tool_synonym_is_used_by_at_least_one_working_phrase(syn, target):
    """A synonym that no phrase can use is dead weight (and a sign it was added for the wrong tool)."""
    owners = {s.full_name for s in SPECS for k, v in s.synonyms if k == syn}
    hits = [c for c in CASES if c[0] == syn and c[2].split(".")[0] in {o.split(".")[0] for o in owners}]
    assert hits, f"no phrase of the owning tool contains {target!r}"


@pytest.mark.parametrize("syn, target", sorted(TOOL_SYNONYMS.items()))
def test_a_synonym_is_not_an_ordinary_word_in_other_tools_phrases(syn, target):
    words = {w for s in SPECS for p in (*s.phrases, *s.keywords, *s.examples) for w in re.findall(r"[a-z']+", re.sub(r"\{\w+\}", " ", p.lower()))}
    assert syn not in words


def test_synonyms_do_not_change_messages_that_already_match():
    """Run the whole labelled corpus with the synonym layer disabled and enabled: every message that matched without it must match identically with it."""
    from app.intent import rule_based
    from tests.corpus import intents as C
    messages = [t for t, _ in [*C.PLAIN, *C.NOISY, *C.WRAPPED, *C.PROMOTED, *C.REAL]] + C.NEGATIVE
    with_synonyms = {m: decide(m, SPECS) for m in messages}
    original = rule_based._best_synonym
    rule_based._best_synonym = lambda text, specs: None
    try:
        without = {m: decide(m, SPECS) for m in messages}
    finally:
        rule_based._best_synonym = original
    changed = [(m, without[m].feature, with_synonyms[m].feature) for m in messages if without[m].kind != "none" and (without[m].feature, without[m].args) != (with_synonyms[m].feature, with_synonyms[m].args)]
    unexpected = [c for c in changed if c[0] not in DELIBERATE_UPGRADES]
    assert not unexpected, f"synonyms changed messages that already matched (add to DELIBERATE_UPGRADES only if the new reading is clearly right): {unexpected}"
    assert all(with_synonyms[m].via == "synonym" for m, _, _ in changed)             # and every change was made by the synonym layer, visibly
    gained = [m for m in messages if without[m].kind == "none" and with_synonyms[m].kind != "none"]
    assert all(with_synonyms[m].via == "synonym" for m in gained)
