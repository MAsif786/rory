"""Webhook authentication: WAHA's HMAC signature (and an optional shared token) must verify before anything is parsed."""
import base64
import hashlib
import hmac
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app import auth, main
from app.settings import Settings, SettingsError

KEY = "s3cret-key-for-tests"
client = TestClient(main.app)
BODY = json.dumps({"event": "message", "session": "default", "payload": {"id": "a1", "from": "1@c.us", "body": "ping"}}).encode()


def signed(body=BODY, key=KEY, algorithm="sha512", encode="hex"):
    digest = hmac.new(key.encode(), body, getattr(hashlib, algorithm)).digest()
    value = digest.hex() if encode == "hex" else base64.b64encode(digest).decode()
    return {"X-Webhook-Hmac": value, "X-Webhook-Hmac-Algorithm": algorithm, "Content-Type": "application/json"}


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def fake(session, chat_id, text):
        out.append(text)

    monkeypatch.setattr(main, "send_text", fake)
    return out


@pytest.fixture
def secured(monkeypatch):
    monkeypatch.setattr(main, "settings", main.settings.model_copy(update={"webhook_hmac_key": KEY}))
    main._auth_warned.clear()


# --- the verifier -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("algorithm", ["sha512", "sha256"])
@pytest.mark.parametrize("encode", ["hex", "base64"])
def test_valid_signatures_pass(algorithm, encode):
    h = {k.lower(): v for k, v in signed(algorithm=algorithm, encode=encode).items()}
    assert auth.verify(BODY, h, {}, KEY) is None


def test_hex_case_does_not_matter_and_the_sign_helper_matches_waha():
    h = {k.lower(): v.upper() if k == "X-Webhook-Hmac" else v for k, v in signed().items()}
    assert auth.verify(BODY, h, {}, KEY) is None
    assert auth.sign(BODY, KEY) == signed()["X-Webhook-Hmac"] and len(auth.sign(BODY, KEY)) == 128         # sha512 hex, like WAHA's example


@pytest.mark.parametrize("what, headers, body, reason", [
    ("wrong key", signed(key="other"), BODY, "mismatch"),
    ("tampered body", signed(), BODY + b" ", "mismatch"),
    ("missing header", {}, BODY, "missing"),
    ("empty header", {"X-Webhook-Hmac": " "}, BODY, "missing"),
    ("md5 is refused", {"X-Webhook-Hmac": "00", "X-Webhook-Hmac-Algorithm": "md5"}, BODY, "unsupported"),
    ("sha1 is refused", {"X-Webhook-Hmac": "00", "X-Webhook-Hmac-Algorithm": "sha1"}, BODY, "unsupported"),
    ("signature of another algorithm", {**signed(algorithm="sha256"), "X-Webhook-Hmac-Algorithm": "sha512"}, BODY, "mismatch"),
    ("garbage", {"X-Webhook-Hmac": "zz" * 64}, BODY, "mismatch")])
def test_bad_signatures_fail(what, headers, body, reason):
    result = auth.verify(body, {k.lower(): v for k, v in headers.items()}, {}, KEY)
    assert result and reason in result, what


def test_nothing_configured_means_everything_passes():
    assert auth.verify(BODY, {}, {}, "", "") is None and not auth.configured("", "")


def test_token_via_header_or_query():
    assert auth.verify(BODY, {"x-webhook-token": "t0k3n"}, {}, token="t0k3n") is None
    assert auth.verify(BODY, {}, {"token": "t0k3n"}, token="t0k3n") is None
    assert auth.verify(BODY, {"x-webhook-token": "nope"}, {}, token="t0k3n") == "bad token"
    assert auth.verify(BODY, {}, {}, token="t0k3n") == "bad token"


def test_when_both_are_configured_both_must_pass():
    h = {k.lower(): v for k, v in signed().items()}
    assert auth.verify(BODY, h, {}, KEY, "t0k3n") == "bad token"
    assert auth.verify(BODY, {**h, "x-webhook-token": "t0k3n"}, {}, KEY, "t0k3n") is None


def test_secrets_are_compared_in_constant_time():
    import inspect
    assert inspect.getsource(auth.verify).count("hmac.compare_digest") == 3                  # hex, base64 and token: never a plain ==


# --- the endpoint -----------------------------------------------------------------------------------------------------------
def test_a_signed_webhook_is_answered(sent, secured):
    assert client.post("/webhook", content=BODY, headers=signed()).status_code == 200
    assert sent == ["pong 🏓"]


@pytest.mark.parametrize("make_headers", [lambda: {}, lambda: signed(key="wrong"), lambda: signed(body=b"{}"), lambda: {"X-Webhook-Hmac": "abc"}],
                         ids=["unsigned", "wrong key", "signature for another body", "garbage"])
def test_unauthenticated_webhooks_get_401_and_nothing_happens(sent, secured, make_headers):
    r = client.post("/webhook", content=BODY, headers={"Content-Type": "application/json", **make_headers()})
    assert r.status_code == 401 and r.json() == {"ok": False, "error": "unauthorized"}               # no hint about which check failed
    assert sent == [] and main.bot.store.get("1@c.us").repeat is None                                   # nothing was parsed, queued or recorded


def test_rejections_are_logged_once_per_reason_not_per_request(sent, secured, caplog):
    with caplog.at_level(logging.WARNING, logger="wa-bot"):
        for _ in range(25):
            client.post("/webhook", content=BODY, headers={"Content-Type": "application/json"})
    assert sum("webhook rejected" in r.getMessage() for r in caplog.records) == 1


def test_a_replayed_signed_message_is_still_answered_once(sent, secured):
    for _ in range(3):
        assert client.post("/webhook", content=BODY, headers=signed()).status_code == 200
    assert sent == ["pong 🏓"]                                                                             # the message id dedup covers replays


def test_authentication_is_checked_before_the_size_limit_matters_and_before_json(sent, secured):
    assert client.post("/webhook", content=b"not json", headers={"Content-Type": "application/json"}).status_code == 401
    big = b"x" * 200_000
    assert client.post("/webhook", content=big, headers=signed(body=big)).status_code == 413            # too big is rejected before it is hashed


def test_token_only_mode(sent, monkeypatch):
    monkeypatch.setattr(main, "settings", main.settings.model_copy(update={"webhook_token": "t0k3n"}))
    assert client.post("/webhook", content=BODY).status_code == 401
    assert client.post("/webhook", content=BODY, headers={"X-Webhook-Token": "t0k3n"}).status_code == 200
    assert client.post("/webhook?token=t0k3n", content=BODY.replace(b"a1", b"a2")).status_code == 200


def test_health_stays_public(secured):
    assert client.get("/health").status_code == 200


def test_open_mode_warns_at_startup(sent, monkeypatch, caplog):
    monkeypatch.setattr(main, "settings", main.settings.model_copy(update={"webhook_hmac_key": "", "webhook_token": ""}))
    with caplog.at_level(logging.WARNING, logger="wa-bot"), TestClient(main.app):
        pass
    assert any("NOT authenticated" in r.getMessage() for r in caplog.records)


def test_no_warning_when_secured(sent, secured, caplog):
    with caplog.at_level(logging.WARNING, logger="wa-bot"), TestClient(main.app):
        pass
    assert not any("NOT authenticated" in r.getMessage() for r in caplog.records)


# --- settings ---------------------------------------------------------------------------------------------------------------
def test_one_variable_can_configure_both_sides():
    assert Settings.from_env({"WHATSAPP_HOOK_HMAC_KEY": "abc"}).webhook_hmac_key == "abc"                # WAHA's own variable, shared via .env
    assert Settings.from_env({"WEBHOOK_HMAC_KEY": "mine", "WHATSAPP_HOOK_HMAC_KEY": "abc"}).webhook_hmac_key == "mine"
    assert Settings.from_env({}).webhook_hmac_key == ""


def test_waha_client_setting():
    assert Settings.from_env({}).waha_client == "fast" and Settings.from_env({"WAHA_CLIENT": "HTTPX"}).waha_client == "httpx"
    with pytest.raises(SettingsError, match="WAHA_CLIENT"):
        Settings.from_env({"WAHA_CLIENT": "carrier-pigeon"})
