import pytest
from fastapi.testclient import TestClient

from app import main
from app.webchat import render


@pytest.fixture
def client():
    main.reset_guards()
    with TestClient(main.app) as c:
        yield c


def test_page_sets_an_anonymous_session_cookie(client):
    r = client.get("/chat")
    assert r.status_code == 200 and "<textarea" in r.text
    assert "rory_web" in client.cookies
    assert "httponly" in r.headers["set-cookie"].lower()


def test_message_gets_the_same_answer_as_whatsapp(client):
    client.get("/chat")
    r = client.post("/chat/message", json={"text": "what is 2+2"})
    assert r.status_code == 200 and r.json()["ok"] and "4" in r.json()["text"]


def test_follow_ups_are_remembered_per_browser(client):
    client.get("/chat")
    client.post("/chat/message", json={"text": "play guess"})
    r = client.post("/chat/message", json={"text": "quit"})
    assert r.json()["ok"]
    other = TestClient(main.app)
    other.get("/chat")
    assert other.cookies.get("rory_web") != client.cookies.get("rory_web")


@pytest.mark.parametrize("body,status", [({"text": ""}, 400), ({"text": 5}, 400), ({}, 400), ({"text": "x" * 5000}, 413)])
def test_bad_input_is_refused_politely(client, body, status):
    client.get("/chat")
    r = client.post("/chat/message", json=body)
    assert r.status_code == status and r.json()["error"]


def test_no_cookie_means_reload(client):
    r = client.post("/chat/message", json={"text": "hi"})
    assert r.status_code == 400 and "Reload" in r.json()["error"]


def test_other_sites_cannot_post(client):
    client.get("/chat")
    r = client.post("/chat/message", json={"text": "hi"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_rate_limit_is_reported(client):
    client.get("/chat")
    codes = [client.post("/chat/message", json={"text": "hi"}).status_code for _ in range(main.settings.rate_limit_max + 2)]
    assert 429 in codes


def test_new_chat_rotates_the_session(client):
    client.get("/chat")
    before = client.cookies.get("rory_web")
    assert client.post("/chat/reset").json()["ok"]
    assert client.cookies.get("rory_web") != before


def test_render_escapes_html_then_adds_whatsapp_markup():
    assert render("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert render("☀️ *Lahore* is _sunny_ ~not~ rainy") == "☀️ <strong>Lahore</strong> is <em>sunny</em> <s>not</s> rainy"
    assert render("2 * 3 * 4 and snake_case_name") == "2 * 3 * 4 and snake_case_name"
    assert render("see https://a.b/c?x=1&y=2.") == 'see <a href="https://a.b/c?x=1&amp;y=2" target="_blank" rel="noopener noreferrer">https://a.b/c?x=1&amp;y=2</a>.'
    assert render('javascript:alert("x")') == "javascript:alert(&quot;x&quot;)"


def test_page_embeds_real_examples_but_not_greetings(client):
    r = client.get("/chat")
    assert "weather in lahore" in r.text


def test_suggestions_come_from_what_rory_accepts(client):
    client.get("/chat")
    assert client.post("/chat/message", json={"text": "flip a coin"}).json()["suggestions"] == ["again"]
    assert client.post("/chat/message", json={"text": "play ttt"}).json()["suggestions"] == ["quit"]
    assert client.post("/chat/message", json={"text": "quit"}).json()["suggestions"] == []
    assert client.post("/chat/message", json={"text": "zxqv blorp"}).json()["suggestions"] == ["help"]


def test_replies_say_which_tool_answered(client):
    client.get("/chat")
    assert client.post("/chat/message", json={"text": "flip a coin"}).json()["label"]
    assert client.post("/chat/message", json={"text": "zxqv blorp"}).json()["label"] is None


def test_typeahead_is_exposed_as_a_combobox_with_a_status_region(client):
    html = client.get("/chat").text
    assert 'role="combobox"' in html and 'aria-controls="suggest"' in html and 'aria-expanded="false"' in html
    assert 'id="suggest" role="listbox"' in html and 'id="status" role="status"' in html


def test_typeahead_examples_say_which_take_a_number(client):
    import json
    import re
    page = client.get("/chat").text
    data = json.loads(re.search(r'id="examples">(.*?)</script>', page, re.S).group(1))
    by_text = {e["text"]: e["amount"] for e in data}
    assert by_text["100 usd to pkr"] and by_text["5 km in miles"]
    assert not by_text["book 1984"] and not by_text["2:255"]
