"""Synonym *suggestions* for tool authors (development time only; the bot never imports this or WordNet).

Given the words a tool's phrases use, find words people might say instead. The result is a list to REVIEW, not to ship blindly:
WordNet knows every sense of a word ("book" -> Bible, bankroll...), so candidates are filtered hard:
  - only the `word_senses` most common senses of the tool word are used (default 1: "book" is the noun, not "reserve");
  - the candidate must itself mean the tool word in one of ITS `candidate_senses` most common senses (default 1: the symmetry guard,
    which drops "word" as a synonym of "news" because that is only its second meaning);
  - candidates that are already words some tool uses, common function words, or capitalised/multi-word lemmas are dropped;
  - a candidate that points at more than one tool word is ambiguous and is reported, not suggested.
The WordNet access is injected (`senses(word) -> [Sense]`) so this logic is tested with a tiny fake; scripts/suggest_synonyms.py wires the real one."""
import re
from dataclasses import dataclass, field
from typing import Callable

STOP = frozenset("""the a an is are was were be been being to of in on at for and or not it its this that these those with from by as what who whom
how why when where which can could will would should shall may might must do does did have has had you your yours me my mine we us our i im am he she
they them his her their there here then than so such just very more most some any all each every other another same into out up down over under
make get set run give take put go come see know let say tell show find use try call ask need feel leave keep play about like much many also around""".split())


@dataclass(frozen=True)
class Sense:
    lemmas: tuple[str, ...]            # words in this sense, lowercase
    gloss: str = ""                    # short definition, shown to the reviewer


@dataclass
class Suggestion:
    word: str                          # the word the tool's phrases use
    synonym: str                       # what a user might say instead
    gloss: str                         # why (the sense they share)


@dataclass
class Report:
    suggestions: list[Suggestion] = field(default_factory=list)
    ambiguous: dict[str, list[str]] = field(default_factory=dict)      # synonym -> tool words it could mean (not suggested)
    skipped_known: int = 0


Senses = Callable[[str], list[Sense]]


def tool_words(phrases_and_keywords: list[str]) -> list[str]:
    """The content words of a tool's phrases/keywords (placeholders and function words removed)."""
    words = {w for src in phrases_and_keywords for w in re.findall(r"[a-z]+", re.sub(r"\{\w+\}", " ", src.lower()))}
    return sorted(w for w in words if len(w) >= 4 and w not in STOP)


def suggest(words: list[str], known: frozenset[str], existing: dict[str, str], senses: Senses, word_senses: int = 1,
            candidate_senses: int = 1) -> Report:
    """Candidates for each word in `words`. `known` = every word some tool already uses; `existing` = synonyms already defined."""
    report, found = Report(), {}
    for word in words:
        for sense in senses(word)[:word_senses]:
            for cand in sense.lemmas:
                if (not re.fullmatch(r"[a-z]{3,}", cand) or cand == word or cand in STOP or cand in existing
                        or cand in {w for w in words if w == cand}):
                    continue
                if cand in known:
                    report.skipped_known += 1
                    continue
                if not any(word in other.lemmas for other in senses(cand)[:candidate_senses]):      # symmetry guard
                    continue
                found.setdefault(cand, {}).setdefault(word, sense.gloss)
    for cand, targets in sorted(found.items()):
        if len(targets) > 1:
            report.ambiguous[cand] = sorted(targets)
        else:
            (word, gloss), = targets.items()
            report.suggestions.append(Suggestion(word, cand, gloss))
    report.suggestions.sort(key=lambda s: (s.word, s.synonym))
    return report


def paste_block(suggestions: list[Suggestion]) -> str:
    items = ", ".join(f'"{s.synonym}": "{s.word}"' for s in suggestions)
    return f"synonyms={{{items}}}" if items else "# no safe suggestions"
