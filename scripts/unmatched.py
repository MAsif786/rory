#!/usr/bin/env python3
"""Review what Rory could not answer, and turn it into improvements.

    scripts/unmatched.py list                  # most frequent unreviewed messages, with the nearest known feature
    scripts/unmatched.py list --kind tool_error --since 7
    scripts/unmatched.py corpus --min 2        # ready-to-paste lines for tests/corpus/intents.py (GAPS)
    scripts/unmatched.py review "bitcoin price" "hii"     # mark handled (hidden from `list` from now on)
    scripts/unmatched.py review --top 10       # mark the 10 listed rows handled
    scripts/unmatched.py stats                 # volume per day / kind, repeat offenders, failing tools
    scripts/unmatched.py prune --days 30       # drop old entries

The inbox is data/unmatched.jsonl (UNMATCHED_PATH). Workflow: list -> decide per message (add a phrase to a tool, add a negative,
add a corpus line, or ignore) -> run the tests -> review the row so it disappears.
"""
import argparse
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.registry import Registry  # noqa: E402
from app.inbox import Recorder, corpus_lines, group_entries, load_reviewed, normalise, read_entries, save_reviewed  # noqa: E402
from app.settings import get_settings  # noqa: E402


def when(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d %b %H:%M")


def main() -> int:
    default_file = get_settings().unmatched_path or "data/unmatched.jsonl"
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=default_file, help=f"inbox file (default {default_file})")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "corpus", "review"):
        p = sub.add_parser(name)
        p.add_argument("--kind", choices=["unmatched", "tool_error"], help="only this kind")
        p.add_argument("--since", type=float, metavar="DAYS", help="only the last N days")
        p.add_argument("--min", type=int, default=1, metavar="N", help="only messages seen at least N times")
        p.add_argument("--limit", type=int, default=30)
        p.add_argument("--all", action="store_true", help="include messages already reviewed")
    sub.choices["review"].add_argument("texts", nargs="*", help="messages to mark reviewed")
    sub.choices["review"].add_argument("--top", type=int, metavar="N", help="mark the N most frequent rows reviewed")
    sub.add_parser("stats")
    pr = sub.add_parser("prune")
    pr.add_argument("--days", type=float, default=30)
    args = ap.parse_args()

    path = Path(args.file)
    reviewed_path = path.with_name(path.stem + ".reviewed.json")
    entries = read_entries(path)
    if args.cmd == "prune":
        print(f"removed {Recorder(path).prune(args.days)} entries older than {args.days:g} days")
        return 0
    if not entries:
        print(f"Inbox is empty ({path}). Nothing to review: either everything was understood, or no messages have arrived yet.")
        return 0

    registry = Registry().discover()
    specs = registry.specs()
    reviewed = set() if getattr(args, "all", False) else load_reviewed(reviewed_path)

    if args.cmd == "stats":
        by_kind, by_day = Counter(e["kind"] for e in entries), Counter(datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d") for e in entries)
        print(f"{len(entries)} entries from {len({e['chat'] for e in entries})} chats, {when(min(e['ts'] for e in entries))} to {when(max(e['ts'] for e in entries))}")
        print("by kind:    " + ", ".join(f"{k} {n}" for k, n in by_kind.most_common()))
        print("per day:    " + ", ".join(f"{d} {n}" for d, n in sorted(by_day.items())[-7:]))
        fails = Counter(e.get("feature") for e in entries if e["kind"] == "tool_error")
        if fails:
            print("failing tools: " + ", ".join(f"{f} x{n}" for f, n in fails.most_common()))
        top = Counter(e["chat"] for e in entries).most_common(3)
        print("busiest chats (hashed): " + ", ".join(f"{c} x{n}" for c, n in top))
        print(f"open (unreviewed) distinct messages: {len(group_entries(entries, specs, load_reviewed(reviewed_path)))}")
        return 0

    since = time.time() - args.since * 86400 if args.since else 0
    kinds = {args.kind} if args.kind else None
    groups = [g for g in group_entries(entries, specs, reviewed, since, kinds) if g.count >= args.min]

    if args.cmd == "list":
        print(f"{len(groups)} distinct message(s) to review" + (" (including reviewed)" if args.all else "") + f", showing {min(len(groups), args.limit)}:\n")
        for g in groups[: args.limit]:
            tag = "TOOL FAILED" if "tool_error" in g.kinds else "not understood"
            print(f"{g.count:>4}x  {g.sample!r}   [{tag}; {len(g.chats)} chat(s); last {when(g.last)}]")
            if "tool_error" in g.kinds:
                print(f"       tool: {', '.join(sorted(g.features))}  (the message was understood; the tool failed: check its upstream / logs)")
            elif g.nearest:
                print(f"       ~ nearest: {g.nearest!r} ({g.suggested})")
        return 0

    if args.cmd == "corpus":
        print(corpus_lines(groups[: args.limit]))
        return 0

    if args.cmd == "review":
        todo = {normalise(t) for t in args.texts} | ({g.text for g in groups[: args.top]} if args.top else set())
        if not todo:
            ap.error("give message texts or --top N")
        save_reviewed(reviewed_path, load_reviewed(reviewed_path) | todo)
        print(f"marked {len(todo)} message(s) as reviewed ({reviewed_path})")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
