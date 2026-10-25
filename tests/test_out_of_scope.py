"""Out-of-scope requests: Rory says plainly what it cannot do, never pretends, and files the demand so new tools can be ranked."""
import pytest

from app.inbox import Recorder, capability_demand
from app.replies import classify_unmatched
from tests.helpers import make_bot, real_registry

REG = real_registry()


@pytest.mark.parametrize("text, category", [
    ("order me a pizza", "orders"), ("book a flight to dubai", "orders"), ("book me a taxi", "orders"), ("where can i buy shoes", "orders"),
    ("set an alarm for 7", "reminders"), ("remind me to call ali", "reminders"), ("call my mother", "calls"), ("can you call ali", "calls"),
    ("send an email to ali", "messaging"), ("play some music", "music"), ("turn on the lights", "smart_home"), ("translate hello to french", "translation"),
    ("write a poem about love", "writing"), ("bitcoin price", "prices"), ("is bitcoin going up", "prices"), ("cricket scores today", "scores"),
    ("directions to the airport", "directions"), ("fix my laptop", "help_with_tasks")])
def test_known_missing_capabilities_are_named(text, category):
    r = classify_unmatched(REG, 1, text)
    assert (r.kind, r.category) == ("out_of_scope", category), r
    assert "I can help with" in r.reply and "weather" in r.reply.lower() and "Send *help*" in r.reply          # always offers what IS possible


@pytest.mark.parametrize("text", ["i need a loan", "can you help me with my homework", "please do my taxes", "i want a holiday"])
def test_requests_without_a_known_category_are_still_honest(text):
    r = classify_unmatched(REG, 1, text)
    assert r.kind == "out_of_scope" and r.category is None and "outside what I can do" in r.reply


@pytest.mark.parametrize("text", ["my phone is slow", "i love music", "football is fun", "the match was great", "i called my mother yesterday", "i bought shoes",
                                  "i like cricket", "it is a nice song", "we booked a table"])
def test_statements_that_merely_mention_a_topic_are_not_requests(text):
    r = classify_unmatched(REG, 1, text)
    assert r.kind == "unmatched" and "can't" not in r.reply and "outside what I can do" not in r.reply, r


@pytest.mark.parametrize("text", ["blah blah blah", "zorblax", "the quick brown fox jumps over the lazy dog", "super", "ok"])
def test_gibberish_and_small_talk_are_not_out_of_scope(text):
    assert classify_unmatched(REG, 1, text).kind == "unmatched"


def test_questions_about_the_bot_get_a_friendly_answer():
    r = classify_unmatched(REG, 1, "what is your favourite colour")
    assert (r.kind, r.category) == ("out_of_scope", "about_bot") and "helper bot" in r.reply


def test_asking_again_says_so_instead_of_repeating():
    first = classify_unmatched(REG, 1, "order me a pizza").reply
    again = classify_unmatched(REG, 2, "order me a pizza").reply
    assert first != again and "still" in again.lower() and "I can help with" in again


def test_a_close_example_still_wins_over_out_of_scope():
    """'play hangmann' is a typo of something we do: suggest it, don't claim it is out of scope."""
    assert "Did you mean" in classify_unmatched(REG, 1, "play hangmann").reply


async def test_the_bot_files_out_of_scope_by_capability(tmp_path):
    inbox = Recorder(tmp_path / "u.jsonl")
    bot, _ = make_bot({})
    bot.recorder = inbox
    for text in ("order me a pizza", "order a burger please", "set an alarm for 7", "zorblax"):
        await bot.respond("c", text)
    kinds = [(e["kind"], e["feature"]) for e in inbox.read()]
    assert kinds[:3] == [("out_of_scope", "orders"), ("out_of_scope", "orders"), ("out_of_scope", "reminders")] and kinds[3][0] == "unmatched"
    assert capability_demand(inbox.read()) == [("orders", 2), ("reminders", 1)]


async def test_the_reply_is_clean_and_in_character(tmp_path):
    bot, _ = make_bot({})
    reply = await bot.respond("c", "order me a pizza")
    assert reply.startswith("🛒 I can't place orders or make bookings.") and "\n\n💡 Send *help*" in reply


def test_review_tool_shows_demand(tmp_path):
    import subprocess, sys
    from pathlib import Path
    inbox = Recorder(tmp_path / "u.jsonl")
    for text, cap in (("order me a pizza", "orders"), ("order a burger", "orders"), ("set an alarm", "reminders")):
        inbox.record("out_of_scope", text, "chat", feature=cap)
    run = lambda *a: subprocess.run([sys.executable, "scripts/unmatched.py", "--file", str(inbox.path), *a], capture_output=True, text=True,
                                    cwd=Path(__file__).resolve().parent.parent).stdout
    assert "missing capabilities users asked for: orders x2, reminders x1" in run("stats")
    listing = run("list", "--kind", "out_of_scope")
    assert "out of scope" in listing and "wanted: orders" in listing
