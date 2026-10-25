"""Group chats: the same person can follow up on Rory's answer without mentioning it again; nobody else can, and chatter never triggers it."""
import pytest
from fastapi.testclient import TestClient

from app import main
from tests import api_fixtures as F
from tests.helpers import FakeHttp

GROUP = "1203630@g.us"
ALICE, BOB = "111@c.us", "222@c.us"
client = TestClient(main.app)


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def rig(monkeypatch):
    """The real bot, offline: fixture upstream data, a recording sender, and a clock the test controls."""
    from types import SimpleNamespace
    http, clock, sent = FakeHttp(F.routes()), Clock(), []

    async def fake_send(session, chat_id, text):
        sent.append((chat_id, text))

    monkeypatch.setattr(main, "send_text", fake_send)
    monkeypatch.setattr(main.bot, "services", SimpleNamespace(http=http))
    monkeypatch.setattr(main.bot.store, "clock", clock)
    n = {"i": 0}

    def say(sender, text, chat=GROUP):
        n["i"] += 1
        payload = {"from": chat, "body": text, "id": f"m{n['i']}"}
        if chat.endswith("@g.us"):
            payload["participant"] = sender
        before = len(sent)
        assert client.post("/webhook", json={"event": "message", "session": "default", "me": {"id": "9@c.us"}, "payload": payload}).status_code == 200
        return [t for _, t in sent[before:]]

    return SimpleNamespace(say=say, sent=sent, http=http, clock=clock)


def cities(rig):
    return [c[1]["name"] for c in rig.http.calls if "geocoding" in c[0]]


# --- the rule ---------------------------------------------------------------------------------------------------------------------
def test_the_same_person_can_follow_up_without_mentioning_the_bot(rig):
    assert "Lahore" in rig.say(ALICE, "rory weather in lahore")[0]
    reply = rig.say(ALICE, "and tomorrow")                                     # no "rory", no @mention
    assert len(reply) == 1 and "(tomorrow)" in reply[0] and cities(rig) == ["lahore", "lahore"]


def test_a_follow_up_can_change_the_place_too(rig):
    rig.say(ALICE, "rory weather in lahore")
    reply = rig.say(ALICE, "what about karachi")
    assert len(reply) == 1 and cities(rig)[-1] == "karachi"


def test_somebody_else_cannot_use_my_follow_up(rig):
    rig.say(ALICE, "rory weather in lahore")
    assert rig.say(BOB, "and tomorrow") == []                                   # Bob was not answered: this is not for Rory
    assert rig.say(BOB, "what about karachi") == []


def test_the_window_closes(rig):
    rig.say(ALICE, "rory weather in lahore")
    rig.clock.t += 100                                                          # default window is 90 s
    assert rig.say(ALICE, "and tomorrow") == []
    rig.say(ALICE, "rory weather in lahore")
    rig.clock.t += 60                                                           # still inside the window
    assert len(rig.say(ALICE, "and tomorrow")) == 1


def test_the_window_can_be_switched_off(rig, monkeypatch):
    monkeypatch.setattr(main, "settings", main.settings.model_copy(update={"group_followup_window": 0}))
    rig.say(ALICE, "rory weather in lahore")
    assert rig.say(ALICE, "and tomorrow") == []


@pytest.mark.parametrize("chatter", ["lol nice", "good morning everyone", "haha yes", "who's coming tonight?", "ok", "👍", "thanks", "hello",
                                     "weather in paris", "100 usd to pkr", "tell me a joke", "play hangman"])
def test_chatter_and_fresh_requests_still_need_a_mention(rig, chatter):
    """Only an exact follow-up of the last answer qualifies. A brand-new request, even a valid one, must still address the bot."""
    rig.say(ALICE, "rory weather in lahore")
    assert rig.say(ALICE, chatter) == []


def test_every_participant_has_their_own_follow_up_context(rig):
    rig.say(ALICE, "rory weather in lahore")
    rig.say(BOB, "rory weather in paris")                                       # Bob's question must not change what Alice's follow-up means
    rig.say(ALICE, "and tomorrow")
    rig.say(BOB, "and tomorrow")
    assert cities(rig) == ["lahore", "paris", "lahore", "paris"]


def test_an_open_question_belongs_to_the_person_it_was_asked(rig):
    assert "place" in rig.say(ALICE, "rory weather")[0].lower()
    assert rig.say(BOB, "multan") == []                                         # Bob answering Alice's question is just chatter
    assert "Lahore" in rig.say(ALICE, "multan")[0] and cities(rig) == ["multan"]


def test_a_group_game_is_shared_by_everyone(rig):
    rig.say(ALICE, "rory play guess")
    main.bot.store.get(GROUP).session.state.secret = 7                          # the secret is random: fix it so Bob's guess can never win by luck
    assert len(rig.say(BOB, "50")) == 1                                         # a guess from anyone, no mention (unchanged behaviour)
    assert main.bot.store.get(GROUP).session.tool == "guess"


def test_repeat_memory_is_per_person(rig):
    rig.say(ALICE, "rory who is einstein")
    assert "Same as a moment ago" in rig.say(ALICE, "rory who is einstein")[0]
    assert "Same as" not in rig.say(BOB, "rory who is einstein")[0]            # Bob asks for the first time


def test_the_bot_still_ignores_a_follow_up_when_the_last_answer_cannot_continue(rig):
    rig.say(ALICE, "rory flip a coin")                                          # the dice tool has no follow-ups
    assert rig.say(ALICE, "and tomorrow") == []


# --- private chats are unchanged ---------------------------------------------------------------------------------------------------
def test_private_follow_ups_work_as_before(rig):
    assert "Lahore" in rig.say(ALICE, "weather in lahore", chat=ALICE)[0]
    assert "(tomorrow)" in rig.say(ALICE, "and tomorrow", chat=ALICE)[0]
    assert cities(rig) == ["lahore", "lahore"]


def test_person_key():
    from app.smart import Bot
    assert Bot.person_key(ALICE, ALICE) == ALICE and Bot.person_key(ALICE, None) == ALICE
    assert Bot.person_key(GROUP, ALICE) == f"{GROUP}|{ALICE}" and Bot.person_key(GROUP, None) == GROUP


# --- no state from chatter ---------------------------------------------------------------------------------------------------------
def test_unaddressed_chatter_creates_no_state_and_no_replies(rig):
    before = len(main.bot.store)
    for i in range(300):
        assert rig.say(f"{i % 50}@c.us", f"lol {i}", chat=f"{i % 20}@g.us") == []
    assert len(main.bot.store) == before


def test_peek_never_creates_or_refreshes():
    from app.core.context import ContextStore
    s = ContextStore(Clock())
    assert s.peek("nobody") is None and len(s) == 0
    s.get("a")
    stamp = s.peek("a").last_seen
    s.clock.t += 10
    s.peek("a")
    assert s.peek("a").last_seen == stamp                                      # peeking does not keep a chat alive


def test_the_follow_up_check_only_looks_at_people_who_were_answered(rig, monkeypatch):
    """Chatter from strangers must not even reach the engine (cost): the check starts with a cheap look at that person's last answer."""
    calls = []
    real = main.bot.engine
    monkeypatch.setattr(main.bot, "engine", lambda *a, **k: calls.append(1) or real(*a, **k))
    for i in range(50):
        rig.say(f"{i}@c.us", "lol", chat=GROUP)
    assert calls == []


def test_a_game_and_a_follow_up_window_do_not_interfere(rig):
    rig.say(ALICE, "rory weather in lahore")
    rig.say(BOB, "rory play guess")
    assert len(rig.say(ALICE, "and tomorrow")) == 1                              # a game is running: "and tomorrow" is a (wrong) guess for the game
    assert main.bot.store.get(GROUP).session.tool == "guess" and cities(rig) == ["lahore"]
