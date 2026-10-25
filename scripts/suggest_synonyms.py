#!/usr/bin/env python3
"""Suggest synonyms for a tool while you develop it (WordNet via nltk: development time only, the bot never loads it).

    scripts/suggest_synonyms.py                    # every installed tool
    scripts/suggest_synonyms.py fun news           # these tools
    scripts/suggest_synonyms.py --words joke bye   # specific words (for a tool you are writing: use the words your phrases use)
    scripts/suggest_synonyms.py --download         # first run: fetch the WordNet data into data/nltk_data (~10 MB)

You get candidates and a `synonyms={...}` line to paste into `Tool(...)`. REVIEW before pasting: keep what a user would really say
for exactly that thing, drop the rest. See docs/ADDING_A_TOOL.md ("Synonyms") for the rules and tests that guard them."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data" / "nltk_data"

from app.core.registry import Registry  # noqa: E402
from app.intent.rule_based import _vocab  # noqa: E402
from app.nlu.lexicon import lexicon  # noqa: E402
from app.nlu.suggest import Sense, paste_block, suggest, tool_words  # noqa: E402


def wordnet(download: bool):
    try:
        import nltk
        from nltk.corpus import wordnet as wn
    except ImportError:
        sys.exit("nltk is not installed. Run: .venv/bin/pip install nltk   (it is listed in requirements-dev.txt)")
    nltk.data.path.insert(0, str(DATA))
    if download:
        DATA.mkdir(parents=True, exist_ok=True)
        nltk.download("wordnet", download_dir=str(DATA), quiet=True)
    try:
        wn.ensure_loaded()
    except LookupError:
        sys.exit("WordNet data is missing. Run once:  scripts/suggest_synonyms.py --download")

    def senses(word: str) -> list[Sense]:
        return [Sense(tuple(l.name().lower() for l in s.lemmas()), s.definition()) for s in wn.synsets(word)]
    return senses


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tools", nargs="*", help="tool names (default: all installed tools)")
    ap.add_argument("--words", nargs="+", help="suggest for these words instead of a tool's phrases")
    ap.add_argument("--word-senses", type=int, default=1, help="how many of YOUR word's most common senses to expand (default 1; more = more candidates, noisier)")
    ap.add_argument("--candidate-senses", type=int, default=1, help="how many of a candidate's most common senses may mean your word (default 1)")
    ap.add_argument("--download", action="store_true", help="download the WordNet data first")
    args = ap.parse_args()

    senses = wordnet(args.download)
    registry = Registry().discover()
    specs = registry.specs()
    known, existing = _vocab(specs), lexicon(specs)

    jobs: list[tuple[str, list[str]]] = []
    if args.words:
        jobs.append(("(given words)", sorted({w.lower() for w in args.words})))
    else:
        unknown = [t for t in args.tools if t not in registry.tools]
        if unknown:
            sys.exit(f"unknown tool(s): {', '.join(unknown)}. Installed: {', '.join(sorted(registry.tools))}")
        for name in args.tools or sorted(registry.tools):
            feats = registry.tools[name].features.values()
            jobs.append((name, tool_words([x for f in feats for x in (*f.spec.phrases, *f.spec.keywords)])))

    for name, words in jobs:
        report = suggest(words, known, existing, senses, args.word_senses, args.candidate_senses)
        print(f"\n== {name}   ({len(words)} words checked)")
        for s in report.suggestions:
            print(f"   {s.synonym:<14} -> {s.word:<12} {s.gloss[:70]}")
        for cand, targets in report.ambiguous.items():
            print(f"   {cand:<14} ?? could mean {', '.join(targets)} (ambiguous: not suggested)")
        print(f"   skipped {report.skipped_known} candidates that are already words some tool uses")
        print("\n   " + paste_block(report.suggestions) + "\n   (review first: keep only what a user would really say for exactly that thing)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
