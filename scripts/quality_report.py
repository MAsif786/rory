#!/usr/bin/env python3
"""Rory quality report: how well does the bot understand, where is it weak, and what should be improved next?

    .venv/bin/python scripts/quality_report.py                    # intent + coverage + speed + offline tool checks
    .venv/bin/python scripts/quality_report.py --tests            # also run the whole pytest suite and summarise it
    .venv/bin/python scripts/quality_report.py --live             # also hit the real APIs (needs the internet)
    .venv/bin/python scripts/quality_report.py --log server.log   # also mine the running bot's log for misses and tool errors
    .venv/bin/python scripts/quality_report.py --json report.json # machine-readable copy

Exit code 0 = every gate passed, 1 = at least one gate failed (so it can run in CI / a pre-push hook).
"""
import argparse
import asyncio
import logging
import difflib
import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("GOOGLE_API_KEY", "offline")
os.environ.setdefault("GOOGLE_CSE_ID", "offline")

from app.intent.rule_based import decide, explain  # noqa: E402
from tests import api_fixtures as F  # noqa: E402
from tests.corpus import intents as C  # noqa: E402
from tests.helpers import lint_reply, make_bot, real_registry  # noqa: E402
from tests.test_intent_engine import fill  # noqa: E402

logging.disable(logging.CRITICAL)           # the report simulates outages on purpose; keep the output readable
GATE_ACCURACY = 0.97
REG = real_registry()
SPECS = REG.specs()
report: dict = {"gates": {}, "improvements": []}


def route(text):
    d = decide(text, SPECS)
    return d.feature if d.kind in ("match", "clarify", "followup") else None


def heading(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def gate(name, ok, detail=""):
    report["gates"][name] = bool(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def improve(text):
    report["improvements"].append(text)


# --- 1. intent detection -------------------------------------------------------------------------------------------------------
def intent_section():
    heading("1. Intent detection (labelled corpus)")
    positive = [*C.PLAIN, *C.NOISY, *C.WRAPPED, *C.PROMOTED, *C.REAL]
    hits, total, misses = defaultdict(int), defaultdict(int), []
    for text, expected in positive:
        total[expected] += 1
        got = route(text)
        hits[expected] += got == expected
        if got != expected:
            misses.append((text, expected, got))
    rows = sorted(total, key=lambda f: hits[f] / total[f])
    print(f"  {'feature':<22}{'ok':>6}{'of':>5}{'acc':>8}")
    for f in rows[:12]:
        print(f"  {f:<22}{hits[f]:>6}{total[f]:>5}{hits[f] / total[f]:>8.0%}")
    if len(rows) > 12:
        print(f"  ... {len(rows) - 12} more features at or above {hits[rows[11]] / total[rows[11]]:.0%}")
    low = [f for f in total if hits[f] / total[f] < GATE_ACCURACY]
    gate(f"every feature >= {GATE_ACCURACY:.0%}", not low, f"below: {low}" if low else f"{len(positive)} messages, {len(total)} features")
    for text, exp, got in misses:
        improve(f"misrouted {text!r}: expected {exp}, got {got}")
    fps = [t for t in C.NEGATIVE if route(t)]
    gate("zero false positives on chatter", not fps, f"{fps}" if fps else f"{len(C.NEGATIVE)} chatter messages")
    bad_args = [(t, f, a) for t, f, a in C.ARGS if (d := decide(t, SPECS)).feature != f or any(d.args.get(k) != v for k, v in a.items())]
    gate("arguments extracted correctly", not bad_args, f"{bad_args[:3]}" if bad_args else f"{len(C.ARGS)} messages")
    still = [(t, e, w) for t, e, w in C.GAPS if route(t) != e]
    fixed = [t for t, e, w in C.GAPS if route(t) == e]
    print(f"\n  Improvement backlog: {len(still)} known gaps still open" + (f", {len(fixed)} now FIXED (move them into the corpus): {fixed}" if fixed else ""))
    for t, e, why in still:
        print(f"    - {t!r} -> should be {e}: {why}")
        improve(f"gap: {t!r} ({why})")
    gate("no stale gaps (fixed ones were promoted)", not fixed)


# --- 2. phrase quality ----------------------------------------------------------------------------------------------------------
def phrase_section():
    heading("2. Phrase health (collisions, thin margins, coverage)")
    ties, thin, selfmiss = [], [], []
    for s in SPECS:
        for src in (*s.phrases, *s.examples):
            text = fill(src)
            ranked = explain(text, SPECS)
            if not ranked or ranked[0][1].full_name != s.full_name and src in s.phrases:
                selfmiss.append((s.full_name, src, ranked[0][1].full_name if ranked else None))
            if len(ranked) > 1 and ranked[0][1].full_name != ranked[1][1].full_name:
                gap = (ranked[0][0][0] - ranked[1][0][0], ranked[0][0][1] - ranked[1][0][1])
                if gap == (0, 0):
                    ties.append((text, ranked[0][1].full_name, ranked[1][1].full_name))
                elif gap[0] == 0 and gap[1] <= 2:
                    thin.append((text, ranked[0][1].full_name, ranked[1][1].full_name, gap[1]))
    gate("every declared phrase routes to its own feature", not selfmiss, f"{selfmiss[:3]}" if selfmiss else f"{sum(len(s.phrases) for s in SPECS)} phrases")
    gate("no order-dependent ties", not ties, f"{ties[:3]}" if ties else "")
    if thin:
        print(f"  {len(thin)} thin margins (winner leads by <= 2 points; fragile if phrases change):")
        for t, a, b, g in thin[:8]:
            print(f"    - {t!r}: {a} beats {b} by {g}")
            improve(f"thin margin on {t!r}: {a} vs {b}")
    no_neg = [s.full_name for s in SPECS if s.kind == "answer" and not s.negatives and s.keywords]
    if no_neg:
        print(f"  Features with keywords but no negatives (risk of false positives): {no_neg}")
        for f in no_neg:
            improve(f"add negatives to {f} (it triggers on keywords)")
    few = [s.full_name for s in SPECS if len(s.examples) < 2 and s.kind == "answer"]
    if few:
        print(f"  Features with a single example (weak regression protection): {few}")
        for f in few:
            improve(f"add a second example to {f}")
    uncovered = sorted({s.full_name for s in SPECS} - {f for _, f in [*C.PLAIN, *C.NOISY, *C.WRAPPED, *C.PROMOTED, *C.REAL]} - {f for _, f, _ in C.ARGS})
    gate("every feature has corpus coverage", not uncovered, f"missing: {uncovered}" if uncovered else "")


# --- 3. speed -------------------------------------------------------------------------------------------------------------------
def speed_section():
    heading("3. Engine speed")
    messages = [t for t, _ in [*C.PLAIN, *C.NOISY, *C.WRAPPED]] + C.NEGATIVE
    decide("warm up", SPECS)
    times = []
    for t in messages * 2:
        start = time.perf_counter()
        decide(t, SPECS)
        times.append((time.perf_counter() - start) * 1000)
    p95 = sorted(times)[int(len(times) * 0.95)]
    print(f"  {len(times)} decisions: mean {statistics.mean(times):.2f} ms, p95 {p95:.2f} ms, max {max(times):.2f} ms")
    gate("p95 decision time < 25 ms", p95 < 25)
    slow = sorted(zip(times, messages * 2), reverse=True)[:3]
    if slow[0][0] > 25:
        improve(f"slow decisions: {[(round(ms), t) for ms, t in slow]}")


# --- 4. offline tool checks ------------------------------------------------------------------------------------------------------
async def offline_section():
    heading("4. Tools with realistic offline data, and with every kind of failure")
    cases = [(s.full_name, ex) for s in SPECS if s.kind == "answer" and s.tool != "link" for ex in s.examples]
    bad = []
    for feature, ex in cases:
        bot, _ = make_bot(F.routes())
        reply = await bot.respond("c", ex)
        problems = lint_reply(reply) or [e for e in ("Something went wrong", "couldn't reach", "didn't get that") if e in reply]
        if problems:
            bad.append((feature, ex, problems))
    gate("every example answers cleanly", not bad, f"{bad[:3]}" if bad else f"{len(cases)} examples")
    matrix = defaultdict(list)
    for mode in ("connect", "timeout", "500", "404", "malformed", "empty"):
        for feature, ex in cases:
            bot, http = make_bot(F.routes(), fail=mode)
            reply = await bot.respond("c", ex)
            if lint_reply(reply) or any(x in reply for x in ("Traceback", "httpx", "unexpected", "upstream says no")):
                matrix[mode].append((feature, reply[:60]))
    gate("no tool leaks or breaks under any failure mode", not matrix, f"{dict(matrix)}" if matrix else "6 failure modes x all tools")
    for mode, items in matrix.items():
        for feature, reply in items:
            improve(f"{feature} mishandles upstream failure {mode!r}: {reply!r}")
    net = []
    for feature, ex in cases:
        bot, http = make_bot(F.routes(), fail="connect")
        reply = await bot.respond("c", ex)
        net.append(feature) if http.calls and "couldn't reach" in reply else None
    print(f"  {len(net)} network tools give a clear 'couldn't reach that service' message during an outage")


# --- 5. pytest -------------------------------------------------------------------------------------------------------------------
def pytest_section(live: bool):
    heading("5. pytest suite" + (" (including LIVE API tests)" if live else ""))
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header"] + (["-m", "live or not live"] if live else [])
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    tail = [l for l in out.stdout.strip().splitlines() if l.strip()][-3:]
    for l in tail:
        print("  " + l)
    failed = re.findall(r"^FAILED (\S+)", out.stdout, re.M)
    for f in failed:
        improve(f"failing test: {f}")
    gate("pytest suite green", out.returncode == 0, f"{len(failed)} failed" if failed else "")


# --- 6. mine the running bot's log ------------------------------------------------------------------------------------------------
def read_log(path: str) -> list[dict]:
    """Log lines as dicts: JSON lines are parsed, plain-text lines are wrapped as {"msg": line}."""
    records = []
    for line in Path(path).read_text(errors="replace").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                records.append(json.loads(line))
                continue
            except ValueError:
                pass
        if line:
            records.append({"msg": line})
    return records


def log_section(path: str):
    heading(f"6. What real users hit (from {path})")
    records = read_log(path) if Path(path).exists() else []
    if not records:
        print("  (log is empty or missing)")
        return
    handled = [r for r in records if r.get("msg") == "handled"]
    if handled:
        outcomes = Counter(r.get("outcome") for r in handled)
        print(f"  {len(handled)} messages handled: " + ", ".join(f"{o} {n}" for o, n in outcomes.most_common()))
        by_feature = defaultdict(list)
        for r in handled:
            if r.get("feature") and r.get("ms") is not None:
                by_feature[r["feature"]].append(r["ms"])
        slow = sorted(((sorted(v)[int(len(v) * 0.95)], f, len(v)) for f, v in by_feature.items()), reverse=True)[:5]
        print("  slowest features (p95 ms, calls): " + ", ".join(f"{f} {ms}ms ({n})" for ms, f, n in slow))
        for ms, f, n in slow:
            if ms > 5000:
                improve(f"{f} is slow for real users: p95 {ms} ms over {n} calls (cache it or add a faster source)")
        failed = outcomes.get("failed", 0)
        gate("no failed messages in the log", failed == 0, f"{failed} failed" if failed else "")
        limited = outcomes.get("rate_limited", 0) + outcomes.get("rate_limited_silent", 0)
        if limited:
            improve(f"{limited} messages were rate limited: check for a looping sender or raise RATE_LIMIT_MAX")
    texts = [r["msg"] for r in records]
    misses = Counter()
    for t in texts:
        if m := re.match(r"unmatched: (['\"].*['\"])$", t):
            misses[m.group(1)] += 1
    errors = Counter(m.group(1) for t in texts if (m := re.match(r"tool handler failed: (\S+)", t)))
    upstream = Counter(m.group(1) for t in texts if (m := re.match(r"upstream problem in (\S+?):", t)))
    print(f"  messages nothing understood: {sum(misses.values())} ({len(misses)} distinct)")
    examples = {ex.lower(): s.full_name for s in SPECS for ex in s.examples}
    for raw, n in misses.most_common(15):
        msg = raw.strip("'\"")
        near = difflib.get_close_matches(msg.lower(), list(examples), n=1, cutoff=0.5)
        hint = f"  ~ looks like {examples[near[0]]} ({near[0]!r})" if near else ""
        print(f"    {n:>3}x {msg!r}{hint}")
        improve(f"real user message unmatched ({n}x): {msg!r}{hint}")
    for title, counter in (("tool crashes (bugs)", errors), ("upstream problems (outages / API changes)", upstream)):
        if counter:
            print(f"  {title}: " + ", ".join(f"{f} x{n}" for f, n in counter.most_common()))
            for f, n in counter.items():
                improve(f"{title.split(' (')[0]}: {f} x{n}")
    gate("no tool crashes in the log", not errors)


def inbox_section(path: str):
    from app.inbox import group_entries, load_reviewed, read_entries
    heading(f"7. Improvement inbox ({path})")
    entries = read_entries(path)
    reviewed_path = Path(path).with_name(Path(path).stem + ".reviewed.json")
    rows = group_entries(entries, SPECS, load_reviewed(reviewed_path))
    print(f"  {len(entries)} recorded, {len(rows)} distinct message(s) still to review (scripts/unmatched.py list)")
    for g in rows[:10]:
        kind = "tool failed" if "tool_error" in g.kinds else "not understood"
        print(f"    {g.count:>3}x {g.sample!r} [{kind}]" + (f"  ~ {g.nearest!r} ({g.suggested})" if g.nearest else ""))
        improve(f"inbox ({g.count}x, {kind}): {g.sample!r}" + (f" ~ {g.suggested}" if g.suggested else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tests", action="store_true", help="also run the pytest suite")
    ap.add_argument("--live", action="store_true", help="also run the live API tests (implies --tests)")
    ap.add_argument("--log", metavar="FILE", help="analyse a bot log for unmatched messages and tool errors")
    ap.add_argument("--json", metavar="FILE", help="write the report as JSON")
    args = ap.parse_args()
    print(f"Rory quality report — {len(REG.tools)} tools, {len(SPECS)} features, {sum(len(s.phrases) for s in SPECS)} phrases")
    intent_section()
    phrase_section()
    speed_section()
    asyncio.run(offline_section())
    if args.tests or args.live:
        pytest_section(args.live)
    if args.log:
        log_section(args.log)
    inbox_file = os.environ.get("UNMATCHED_PATH") or "data/unmatched.jsonl"
    if Path(inbox_file).exists():
        inbox_section(inbox_file)
    heading("Improvement candidates" + f" ({len(report['improvements'])})")
    for i, item in enumerate(report["improvements"], 1):
        print(f"  {i:>2}. {item}")
    if not report["improvements"]:
        print("  none found")
    failed = [g for g, ok in report["gates"].items() if not ok]
    print(f"\n{'ALL GATES PASSED' if not failed else 'GATES FAILED: ' + ', '.join(failed)}  ({len(report['gates']) - len(failed)}/{len(report['gates'])})")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
