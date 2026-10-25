"""Webhook authentication: only WAHA (or whoever holds the secret) may talk to /webhook.

WAHA signs each webhook when a key is configured (`WHATSAPP_HOOK_HMAC_KEY`): header `X-Webhook-Hmac` = HMAC of the RAW request body
(hex), `X-Webhook-Hmac-Algorithm` = sha512. We verify it with a constant-time comparison. A simpler shared token (`X-Webhook-Token`
header or `?token=` query, e.g. via WAHA's custom headers) is supported too. With neither configured the endpoint stays open
(the old behaviour) and the app logs a warning at startup. Failures reveal nothing about which check failed."""
import base64
import hashlib
import hmac
from typing import Mapping

ALGORITHMS = {"sha256": hashlib.sha256, "sha512": hashlib.sha512}      # nothing weaker (no md5 / sha1) is ever accepted


def sign(body: bytes, key: str, algorithm: str = "sha512") -> str:
    """The hex digest WAHA would send (used by tests and the stress script)."""
    return hmac.new(key.encode(), body, ALGORITHMS[algorithm]).hexdigest()


def configured(hmac_key: str, token: str) -> bool:
    return bool(hmac_key or token)


def verify(body: bytes, headers: Mapping[str, str], query: Mapping[str, str], hmac_key: str = "", token: str = "") -> str | None:
    """None when the request is authentic, otherwise a short internal reason (logged, never sent to the caller).
    Every configured check must pass; if nothing is configured everything passes."""
    if hmac_key:
        algorithm = (headers.get("x-webhook-hmac-algorithm") or "sha512").lower()
        given = (headers.get("x-webhook-hmac") or "").strip()
        if algorithm not in ALGORITHMS:
            return f"unsupported hmac algorithm {algorithm[:20]!r}"
        if not given:
            return "missing X-Webhook-Hmac"
        digest = hmac.new(hmac_key.encode(), body, ALGORITHMS[algorithm]).digest()
        # WAHA documents a hex digest; base64 is accepted as well so a proxy or a different WAHA version cannot lock the bot out
        if not (hmac.compare_digest(given.lower(), digest.hex()) or hmac.compare_digest(given, base64.b64encode(digest).decode())):
            return "hmac mismatch"
    if token:
        given_token = headers.get("x-webhook-token") or query.get("token") or ""
        if not hmac.compare_digest(given_token.encode(), token.encode()):
            return "bad token"
    return None
