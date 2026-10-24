import pytest
from fastapi.testclient import TestClient

from app import main, replies

client = TestClient(main.app)


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def fake(session, chat_id, text):
        out.append((session, chat_id, text))

    monkeypatch.setattr(main, "send_text", fake)
    return out


def event(body="hi", **payload):
    return {"event": "message", "session": "default", "payload": {"from": "123@c.us", "body": body, **payload}}


def test_health():
    assert client.get("/health").json() == {"ok": True}


@pytest.mark.parametrize("text, reply", [("ping", "pong 🏓")])
def test_replies(sent, text, reply):
    assert client.post("/webhook", json=event(text)).json() == {"ok": True}
    assert sent == [("default", "123@c.us", reply)]


def test_unmatched_gets_fallback_with_real_examples(sent):
    client.post("/webhook", json=event("blah blah"))
    assert sent[0][2].startswith("🤔 I didn't get that.") and "💡 Try _" in sent[0][2]


def test_greeting_leads_to_the_menu(sent):
    client.post("/webhook", json=event("Hello"))
    assert sent[0][2].startswith(tuple(replies.GREETING)) and "🏠 *Home*" in sent[0][2]


def test_ignores_own_empty_and_other_events(sent):
    client.post("/webhook", json=event("hi", fromMe=True))
    client.post("/webhook", json=event(""))
    client.post("/webhook", json={"event": "session.status", "payload": {}})
    assert sent == []
