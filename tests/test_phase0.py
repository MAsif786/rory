"""Phase 0 (customer safety): non-blocking webhook, duplicates, rate limits, bounded memory, group etiquette, settings, structured logs."""
import asyncio
import json
import logging
import time

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from app import main
from app.core.context import ContextStore
from app.groups import address, is_group
from app.guards import KeyedLocks, RateLimiter, Seen
from app.logsetup import JsonFormatter, TextFormatter, chat_ref
from app.settings import Settings, SettingsError

client = TestClient(main.app)
GROUP = "120363@g.us"


def event(body="ping", chat="123@c.us", id=None, **payload):
    p = {"from": chat, "body": body, **payload}
    if id is not None:
        p["id"] = id
    return {"event": "message", "session": "default", "me": {"id": "9230000@c.us"}, "payload": p}


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def fake(session, chat_id, text):
        out.append((chat_id, text))

    monkeypatch.setattr(main, "send_text", fake)
    return out


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


# --- 0.1 acknowledge immediately, reply in the background ---------------------------------------------------------------
def test_webhook_returns_before_a_slow_tool_finishes(sent, monkeypatch):
    async def slow(chat_id, text):
        await asyncio.sleep(0.3)
        return "slow answer"
    monkeypatch.setattr(main, "reply_for", slow)
    with TestClient(main.app) as c:                                     # the context manager runs the lifespan: the worker pool is up
        start = time.perf_counter()
        assert c.post("/webhook", json=event("anything")).json() == {"ok": True}
        assert time.perf_counter() - start < 0.15 and sent == []        # WAHA already has its answer; the reply is still pending
    assert sent == [("123@c.us", "slow answer")]                        # leaving the context drains the queue


def test_without_a_worker_pool_the_webhook_falls_back_to_background_tasks(sent):
    assert main.queue is None                                           # the module-level client above does not run the lifespan
    assert client.post("/webhook", json=event("ping")).json() == {"ok": True}
    assert sent == [("123@c.us", "pong 🏓")]


def test_the_worker_pool_handles_many_chats_at_once(sent, monkeypatch):
    async def slow(chat_id, text):
        await asyncio.sleep(0.2)
        return f"done {text}"
    monkeypatch.setattr(main, "reply_for", slow)
    with TestClient(main.app) as c:
        start = time.perf_counter()
        for i in range(20):
            c.post("/webhook", json=event(f"m{i}", chat=f"{i}@c.us", id=f"w{i}"))
        acked = time.perf_counter() - start
    assert acked < 0.5 and len(sent) == 20                              # 20 x 0.2 s of work was done concurrently, acknowledged instantly
    assert sorted(t for _, t in sent) == sorted(f"done m{i}" for i in range(20))


def test_messages_of_one_chat_keep_their_order_through_the_worker_pool(sent, monkeypatch):
    async def reply(chat_id, text):
        await asyncio.sleep(0.15 if text == "first" else 0)             # the first message is the slowest
        return text
    monkeypatch.setattr(main, "reply_for", reply)
    with TestClient(main.app) as c:
        for i, text in enumerate(("first", "second", "third")):
            c.post("/webhook", json=event(text, id=f"o{i}"))
    assert [t for _, t in sent] == ["first", "second", "third"]


def test_a_full_queue_asks_waha_to_retry(sent, monkeypatch):
    async def slow(chat_id, text):
        await asyncio.sleep(0.5)
        return "ok"
    monkeypatch.setattr(main, "reply_for", slow)
    with TestClient(main.app) as c:
        main.queue._maxsize = 2                                         # tiny queue; the workers are all busy with the first messages
        codes = [c.post("/webhook", json=event("x", chat=f"{i}@c.us", id=f"q{i}")).status_code for i in range(80)]
    assert 503 in codes and codes.count(200) >= 2 and set(codes) <= {200, 503}


@pytest.mark.parametrize("kwargs, status", [
    ({"content": b"not json"}, 400), ({"content": b""}, 400), ({"json": []}, 400), ({"json": "text"}, 400), ({"json": 42}, 400),
    ({"content": b"x" * 200_000}, 413), ({"content": b'{"event": "message", "payload": "' + b"a" * 200_000 + b'"}'}, 413)])
def test_malformed_requests_get_a_4xx_never_a_500(sent, kwargs, status):
    assert client.post("/webhook", **kwargs).status_code == status
    assert sent == []


@pytest.mark.parametrize("body", [
    {"event": "message"}, {"event": "message", "payload": None}, {"event": "message", "payload": []}, {"event": "message", "payload": "x"},
    {"event": "message", "payload": {"from": 5, "body": 7}}, {"event": "message", "payload": {"from": "1@c.us", "body": ["a"]}},
    {"event": "message", "payload": {"from": "1@c.us", "body": "ping", "id": 12345, "participant": 5, "fromMe": "yes"}, "me": "x", "session": 7},
    {"event": ["message"]}, {"payload": {"from": "1@c.us", "body": "ping"}}, {}])
def test_oddly_shaped_events_are_ignored_not_crashed_on(sent, body):
    assert client.post("/webhook", json=body).status_code == 200
    assert all(t == "pong 🏓" for _, t in sent) and len(sent) <= 1       # at worst the one well-formed-enough "ping" is answered


def test_a_crashing_bot_does_not_break_the_webhook(sent, monkeypatch, caplog):
    async def boom(chat_id, text):
        raise RuntimeError("router bug")
    monkeypatch.setattr(main, "reply_for", boom)
    with caplog.at_level(logging.INFO, logger="wa-bot"):
        assert client.post("/webhook", json=event("hello")).json() == {"ok": True}
    assert sent == [] and any(r.outcome == "failed" for r in caplog.records if hasattr(r, "outcome"))


def test_waha_being_down_is_logged_not_raised(monkeypatch, caplog):
    async def down(session, chat_id, text):
        raise ConnectionError("waha down")
    monkeypatch.setattr(main, "send_text", down)
    with caplog.at_level(logging.INFO, logger="wa-bot"):
        assert client.post("/webhook", json=event("ping")).json() == {"ok": True}
    assert any(getattr(r, "outcome", "") == "failed" for r in caplog.records)


# --- 0.2 duplicates --------------------------------------------------------------------------------------------------------
def test_a_retried_webhook_is_answered_once(sent):
    for _ in range(3):
        client.post("/webhook", json=event("ping", id="false_123@c.us_ABC"))
    client.post("/webhook", json=event("ping", id="false_123@c.us_DEF"))
    assert [t for _, t in sent] == ["pong 🏓", "pong 🏓"]


def test_messages_without_an_id_are_never_treated_as_duplicates(sent):
    client.post("/webhook", json=event("ping"))
    client.post("/webhook", json=event("ping"))
    assert len(sent) == 2


def test_seen_forgets_after_its_ttl_and_stays_bounded():
    clock = Clock()
    s = Seen(ttl=60, maxsize=3, clock=clock)
    assert not s.duplicate("a") and s.duplicate("a")
    clock.t += 61
    assert not s.duplicate("a")                                         # expired: a real new message with a recycled id is fine
    for i in range(10):
        s.duplicate(f"id{i}")
    assert len(s._ids) <= 3


# --- 0.3 rate limit --------------------------------------------------------------------------------------------------------
def test_rate_limiter_notifies_once_then_drops_then_recovers():
    clock = Clock()
    r = RateLimiter(3, 30, clock)
    assert [r.check("u") for _ in range(3)] == ["ok"] * 3
    assert [r.check("u") for _ in range(4)] == ["notify", "drop", "drop", "drop"]
    assert r.check("other") == "ok"                                      # per sender
    clock.t += 31
    assert r.check("u") == "ok"                                          # window passed
    for _ in range(2):
        r.check("u")
    assert r.check("u") == "notify"                                      # and can notify again later


def test_rate_limit_through_the_webhook(sent, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(main, "limiter", RateLimiter(12, 30, clock))
    for i in range(16):
        client.post("/webhook", json=event("ping", id=f"m{i}"))
    texts = [t for _, t in sent]
    assert texts.count("pong 🏓") == 12 and texts.count(main.RATE_NOTICE) == 1 and len(texts) == 13   # one notice, then silence


def test_in_a_group_each_participant_has_their_own_limit(sent, monkeypatch):
    monkeypatch.setattr(main, "limiter", RateLimiter(2, 30, Clock()))
    for i in range(3):
        client.post("/webhook", json=event("!ping", chat=GROUP, id=f"a{i}", participant="111@c.us"))
    client.post("/webhook", json=event("!ping", chat=GROUP, id="b0", participant="222@c.us"))
    assert [t for _, t in sent].count("pong 🏓") == 3                    # 2 for the first sender, 1 for the second


def test_overlong_messages_get_a_polite_refusal(sent):
    client.post("/webhook", json=event("a " * (main.settings.max_message_chars)))
    assert sent and "too long" in sent[0][1]


# --- 0.4 memory stays bounded ----------------------------------------------------------------------------------------------
def test_idle_chats_are_forgotten():
    clock = Clock()
    store = ContextStore(clock, idle_ttl=100, max_chats=1000)
    store.SWEEP_EVERY = 1
    store.get("old")
    clock.t += 200
    store.get("new")
    assert "old" not in store._chats and "new" in store._chats


def test_least_recently_used_chats_go_first_when_over_the_cap():
    store = ContextStore(Clock(), idle_ttl=10**6, max_chats=50)
    for i in range(50):
        store.get(f"c{i}")
    store.get("c0")                                                      # c0 becomes the most recent
    store.get("c-new")
    assert "c0" in store._chats and "c1" not in store._chats and len(store) == 50


def test_ten_thousand_chats_cannot_grow_memory_without_bound():
    store = ContextStore(Clock(), idle_ttl=10**6, max_chats=100)
    for i in range(10_000):
        store.get(f"c{i}")
    assert len(store) == 100


def test_a_cold_chat_that_returns_starts_fresh_but_an_active_one_keeps_its_game():
    clock = Clock()
    store = ContextStore(clock, idle_ttl=100, max_chats=1000)
    from app.core.context import ActiveSession
    store.set_session("a", ActiveSession("guess", object()))
    clock.t += 50
    assert store.get("a").session                                        # active: kept (and refreshed)
    clock.t += 150
    assert store.get("a").session is None                                # idle past the TTL: forgotten


# --- 0.5 group etiquette ---------------------------------------------------------------------------------------------------
ME = "9230000@c.us"


@pytest.mark.parametrize("text, payload, expected", [
    ("weather in lahore", {"from": "1@c.us"}, "weather in lahore"),                                   # private: untouched
    ("weather in lahore", {"from": GROUP}, None),                                                      # group, not addressed: silent
    ("lol nice one", {"from": GROUP}, None),
    ("rory weather in lahore", {"from": GROUP}, "weather in lahore"),
    ("Rory, what's the weather", {"from": GROUP}, "what's the weather"),
    ("hey @rory flip a coin", {"from": GROUP}, "flip a coin"),
    ("@9230000 weather in lahore", {"from": GROUP, "mentionedIds": [ME]}, "weather in lahore"),
    ("weather in lahore @9230000", {"from": GROUP, "_data": {"mentionedJidList": [ME]}}, "weather in lahore"),
    ("!ping", {"from": GROUP}, "ping"), ("/menu", {"from": GROUP}, "menu"),
    ("rorya is my cousin", {"from": GROUP}, None),                                                     # a longer word is not the name
])
def test_group_addressing(text, payload, expected):
    assert address(text, payload, ME, "rory", "mention") == expected


def test_group_modes_and_engaged_conversations():
    g = {"from": GROUP}
    assert address("hello", g, ME, "rory", "off") is None and address("hello", g, ME, "rory", "all") == "hello"
    assert address("a", g, ME, "rory", "mention", engaged=True) == "a"        # mid-game answers need no mention
    assert is_group(GROUP) and not is_group("123@c.us")


def test_group_messages_through_the_webhook(sent):
    client.post("/webhook", json=event("hi everyone", chat=GROUP, id="g1"))                 # chatter between people: silent
    client.post("/webhook", json=event("rory ping", chat=GROUP, id="g2"))
    client.post("/webhook", json=event("play hangman", chat="1@c.us", id="p1"))           # private chat is unaffected
    assert [c for c, _ in sent] == [GROUP, "1@c.us"] and sent[0][1] == "pong 🏓"


def test_a_group_game_continues_without_mentions(sent):
    client.post("/webhook", json=event("rory play guess", chat=GROUP, id="x1"))
    assert main.bot.store.get(GROUP).session
    client.post("/webhook", json=event("50", chat=GROUP, id="x2", participant="111@c.us"))
    assert len(sent) == 2                                                                   # the guess was a reply to the game


@pytest.mark.parametrize("payload", [{"fromMe": True}, {"from": "status@broadcast"}, {"body": ""}, {"body": "   "}])
def test_own_empty_and_broadcast_messages_are_ignored(sent, payload):
    ev = event("ping")
    ev["payload"].update(payload)
    client.post("/webhook", json=ev)
    assert sent == []


def test_group_mode_off_silences_groups(sent, monkeypatch):
    monkeypatch.setattr(main, "settings", main.settings.model_copy(update={"group_mode": "off"}))
    client.post("/webhook", json=event("rory ping", chat=GROUP, id="o1"))
    assert sent == []


# --- per-chat ordering -----------------------------------------------------------------------------------------------------
async def test_one_chat_is_processed_in_order_even_if_the_first_is_slow(monkeypatch):
    order = []
    locks = KeyedLocks()

    async def handle(name, delay):
        async with locks("chat"):
            await asyncio.sleep(delay)
            order.append(name)

    await asyncio.gather(handle("first", 0.1), handle("second", 0.0), handle("third", 0.0))
    assert order == ["first", "second", "third"] and locks._locks == {}      # in arrival order, and no lock objects left behind


async def test_different_chats_run_in_parallel():
    locks = KeyedLocks()

    async def handle(key):
        async with locks(key):
            await asyncio.sleep(0.2)

    start = time.perf_counter()
    await asyncio.gather(*(handle(f"c{i}") for i in range(10)))
    assert time.perf_counter() - start < 0.5


async def test_weather_then_place_sent_back_to_back_still_works(sent, monkeypatch):
    """The classic race: 'weather' asks a question, 'lahore' answers it. Concurrent processing could answer before the question is stored."""
    async def routes_delay(chat_id, text):
        await asyncio.sleep(0.05 if text == "weather" else 0)
        return await main.bot.respond(chat_id, text)
    monkeypatch.setattr(main, "reply_for", routes_delay)
    jobs = [main.Job("default", "7@c.us", "7@c.us", t, None) for t in ("weather", "lahore")]
    await asyncio.gather(*(main.process(j) for j in jobs))
    assert sent[0][1] == "📍 Which place?" or "place" in sent[0][1].lower()
    assert len(sent) == 2 and "place" not in sent[1][1].lower()


# --- 0.6 settings ----------------------------------------------------------------------------------------------------------
def test_settings_defaults_and_environment_override():
    s = Settings.from_env({})
    assert (s.group_mode, s.rate_limit_max, s.rate_limit_window, s.bot_name) == ("mention", 12, 30, "rory") and s.waha_url.startswith("http")
    s = Settings.from_env({"WAHA_URL": "https://waha.example.com/", "RATE_LIMIT_MAX": "5", "GROUP_MODE": "ALL", "BOT_NAME": " Rory ", "LOG_JSON": "false"})
    assert (s.waha_url, s.rate_limit_max, s.group_mode, s.bot_name, s.log_json) == ("https://waha.example.com", 5, "all", "rory", False)


def test_bad_configuration_fails_fast_and_names_every_problem():
    with pytest.raises(SettingsError) as e:
        Settings.from_env({"WAHA_URL": "localhost:3000", "RATE_LIMIT_MAX": "zero", "GROUP_MODE": "shout", "MAX_CHATS": "1"})
    msg = str(e.value)
    for var in ("WAHA_URL", "RATE_LIMIT_MAX", "GROUP_MODE", "MAX_CHATS"):
        assert var in msg
    assert "Invalid configuration" in msg


def test_empty_values_in_env_mean_use_the_default():
    assert Settings.from_env({"WAHA_URL": "", "RATE_LIMIT_MAX": ""}).rate_limit_max == 12


# --- 0.7 structured logs ---------------------------------------------------------------------------------------------------
def test_each_message_produces_one_structured_line_without_the_phone_number(sent, caplog):
    with caplog.at_level(logging.INFO):
        client.post("/webhook", json=event("25*8", chat="923001234567@c.us", id="l1"))
        client.post("/webhook", json=event("blah blah blah blah blah blah", chat="923001234567@c.us", id="l2"))
    handled = [r for r in caplog.records if r.getMessage() == "handled"]
    assert len(handled) == 2
    a, b = handled
    assert (a.kind, a.feature, a.outcome) == ("answer", "calc.calc", "replied")
    assert b.kind == "fallback" and b.outcome == "replied"
    assert a.chat == chat_ref("923001234567@c.us") and isinstance(a.ms, int) and a.in_chars == 4
    assert "923001234567" not in json.dumps([r.__dict__ for r in handled], default=str)           # the raw number is never logged


def test_json_formatter_emits_parseable_lines_with_extra_fields():
    rec = logging.LogRecord("wa-bot", logging.INFO, __file__, 1, "handled", (), None)
    rec.chat, rec.ms, rec.feature = "abc", 12, "weather.current"
    data = json.loads(JsonFormatter().format(rec))
    assert data["msg"] == "handled" and data["chat"] == "abc" and data["ms"] == 12 and data["level"] == "INFO" and data["ts"].endswith("+00:00")
    assert "chat=abc" in TextFormatter().format(rec)


def test_exceptions_are_logged_as_a_json_field():
    try:
        raise ValueError("bad")
    except ValueError:
        import sys
        rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "oops", (), sys.exc_info())
    assert "ValueError: bad" in json.loads(JsonFormatter().format(rec))["exc"]


def test_unmatched_messages_are_still_logged_for_the_report(sent, caplog):
    with caplog.at_level(logging.INFO):
        client.post("/webhook", json=event("zxqv wibble", id="u1"))
    assert any("unmatched" in r.getMessage() for r in caplog.records)
