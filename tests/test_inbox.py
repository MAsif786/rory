"""The improvement inbox: what gets recorded, what never does, and how it is reviewed."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.inbox import Recorder, corpus_lines, group_entries, load_reviewed, nearest_example, normalise, read_entries, save_reviewed
from app.logsetup import chat_ref
from tests import api_fixtures as F
from tests.helpers import make_bot, real_registry

SPECS = real_registry().specs()


class Clock:
    t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def inbox(tmp_path):
    return Recorder(tmp_path / "unmatched.jsonl", Clock())


def bot_with(inbox, routes=None, fail=None):
    bot, http = make_bot(routes if routes is not None else F.routes(), fail=fail)
    bot.recorder = inbox
    return bot


# --- what is recorded -----------------------------------------------------------------------------------------------------
async def test_unmatched_messages_are_recorded_with_the_nearest_feature(inbox):
    bot = bot_with(inbox)
    await bot.respond("923001234567@c.us", "wtr in lahore")
    [e] = inbox.read()
    assert (e["kind"], e["text"], e["nearest"], e["feature"]) == ("unmatched", "wtr in lahore", "weather in lahore", "weather.current")
    assert e["chat"] == chat_ref("923001234567@c.us") and "923001234567" not in json.dumps(e)       # the number is never stored
    assert e["group"] is False


async def test_matched_messages_and_small_talk_are_not_recorded_as_misses(inbox):
    bot = bot_with(inbox)
    for text in ("25*8", "hello", "ping", "weather in lahore", "help"):
        await bot.respond("c", text)
    assert inbox.read() == []


async def test_tool_failures_are_recorded_against_the_feature(inbox):
    bot = bot_with(inbox, fail="connect")
    await bot.respond("c", "weather in lahore")
    [e] = inbox.read()
    assert (e["kind"], e["feature"], e["note"], e["text"]) == ("tool_error", "weather.current", "network", "weather in lahore")


async def test_user_mistakes_are_not_tool_errors(inbox):
    bot = bot_with(inbox)
    await bot.respond("c", "roll 99d6")                                  # "Between 1 and 20 dice": the user's input, not a failure
    await bot.respond("c", "capital of atlantis")
    assert [e for e in inbox.read() if e["kind"] == "tool_error"] == []


async def test_group_messages_are_flagged(inbox):
    bot = bot_with(inbox)
    await bot.respond("1203@g.us", "zxqv wibble")
    assert inbox.read()[0]["group"] is True


def test_recording_can_be_switched_off_and_never_raises(tmp_path):
    Recorder(None).record("unmatched", "x", "c")                         # disabled: no file, no error
    blocked = tmp_path / "a_file"
    blocked.write_text("")
    Recorder(blocked / "sub" / "x.jsonl").record("unmatched", "x", "c")   # unwritable path: swallowed, the conversation goes on
    Recorder(tmp_path / "ok.jsonl").record("unmatched", "   ", "c")       # blank text is not worth keeping
    assert not (tmp_path / "ok.jsonl").exists()


def test_a_half_written_line_does_not_break_reading(tmp_path):
    p = tmp_path / "u.jsonl"
    p.write_text('{"ts": 1, "kind": "unmatched", "text": "ok", "chat": "a"}\n{"ts": 2, "kind": "unm\n\n')
    assert len(read_entries(p)) == 1


def test_old_entries_are_pruned(inbox):
    clock = inbox.clock
    inbox.record("unmatched", "old message", "c")
    clock.t += 40 * 86400
    inbox.record("unmatched", "new message", "c")
    assert inbox.prune(30) == 1 and [e["text"] for e in inbox.read()] == ["new message"]


# --- review: grouping, suggestions, reviewed state ----------------------------------------------------------------------------
def test_repeats_collapse_into_one_row_with_a_count(inbox):
    for text, chat in (("Bitcoin price?", "a"), ("bitcoin   price", "b"), ("BITCOIN PRICE!!", "a"), ("zorblax", "a")):
        inbox.record("unmatched", text, chat)
    rows = group_entries(inbox.read(), SPECS)
    assert [(g.text, g.count, len(g.chats)) for g in rows] == [("bitcoin price", 3, 2), ("zorblax", 1, 1)]


def test_reviewed_messages_disappear_until_included(inbox, tmp_path):
    inbox.record("unmatched", "bitcoin price", "a")
    inbox.record("unmatched", "zorblax", "a")
    reviewed_file = tmp_path / "r.json"
    save_reviewed(reviewed_file, {normalise("Bitcoin price!")})
    assert [g.text for g in group_entries(inbox.read(), SPECS, load_reviewed(reviewed_file))] == ["zorblax"]
    assert len(group_entries(inbox.read(), SPECS)) == 2
    assert load_reviewed(tmp_path / "missing.json") == set()


def test_filters_by_kind_and_age(inbox):
    inbox.record("unmatched", "old thing", "a")
    inbox.clock.t += 10 * 86400
    inbox.record("tool_error", "weather in lahore", "a", feature="weather.current")
    rows = group_entries(inbox.read(), SPECS, since=inbox.clock.t - 86400)
    assert [g.text for g in rows] == ["weather in lahore"]
    assert [g.text for g in group_entries(inbox.read(), SPECS, kinds={"unmatched"})] == ["old thing"]


@pytest.mark.parametrize("text, example", [("wtr in lahore", "weather in lahore"), ("tel me a jok", "tell me a joke"), ("completely unrelated gibberish zzz", None)])
def test_nearest_example_suggestion(text, example):
    found = nearest_example(text, SPECS)
    assert (found[0] if found else None) == example


def test_corpus_lines_are_pasteable_python(inbox):
    inbox.record("unmatched", 'say "hi" to wtr in lahore', "a")
    inbox.record("tool_error", "weather in lahore", "a", feature="weather.current")
    text = corpus_lines(group_entries(inbox.read(), SPECS))
    entries = eval("[" + "\n".join(l for l in text.splitlines() if not l.startswith("#")) + "]")       # each line is a valid tuple
    assert all(len(e) == 3 for e in entries) and any("tool failed" in e[2] for e in entries)


# --- the command-line tool ----------------------------------------------------------------------------------------------------
def run_cli(file, *args):
    out = subprocess.run([sys.executable, "scripts/unmatched.py", "--file", str(file), *args], capture_output=True, text=True,
                         cwd=Path(__file__).resolve().parent.parent)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_cli_empty_inbox_is_friendly(tmp_path):
    assert "Inbox is empty" in run_cli(tmp_path / "none.jsonl", "list")


def test_cli_list_review_corpus_stats_prune(tmp_path):
    inbox = Recorder(tmp_path / "u.jsonl")
    for text in ("wtr in lahore", "wtr in lahore", "zorblax"):
        inbox.record("unmatched", text, "chat-a")
    inbox.record("tool_error", "weather in karachi", "chat-b", feature="weather.current", note="network")
    listing = run_cli(inbox.path, "list")
    assert "3 distinct message(s)" in listing
    assert "2x  'wtr in lahore'" in listing and "nearest: 'weather in lahore' (weather.current)" in listing and "TOOL FAILED" in listing
    assert "zorblax" in run_cli(inbox.path, "list", "--kind", "unmatched") and "karachi" not in run_cli(inbox.path, "list", "--kind", "unmatched")
    assert "0 distinct" in run_cli(inbox.path, "list", "--min", "3")
    assert "marked 1" in run_cli(inbox.path, "review", "Wtr in Lahore!")
    assert "wtr in lahore" not in run_cli(inbox.path, "list") and "wtr in lahore" in run_cli(inbox.path, "list", "--all")
    assert '("zorblax", None' in run_cli(inbox.path, "corpus", "--min", "1")
    stats = run_cli(inbox.path, "stats")
    assert "4 entries from 2 chats" in stats and "failing tools: weather.current x1" in stats
    assert "removed 0 entries" in run_cli(inbox.path, "prune", "--days", "30")
