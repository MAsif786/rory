"""Shared test machinery: a realistic fake HTTP layer, a reply linter, and ready-made bots over the real tools."""
import asyncio
import re
from types import SimpleNamespace

import httpx

from app.core.context import ContextStore
from app.core.dispatcher import Dispatcher
from app.core.registry import Registry
from app.intent.rule_based import decide
from app.smart import Bot

_REGISTRY: Registry | None = None


def real_registry() -> Registry:
    """Every tool in tools/ (cached: discovery imports every tool)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = Registry().discover()
    return _REGISTRY


class FakeHttp:
    """httpx-shaped client for offline tests. `routes` maps a URL fragment to a JSON body, a text body (str),
    a callable(url, params) -> body, or a (status, body) pair; `fail` makes every call fail the way a real network would:
      connect | timeout | slow (hangs) | 500 | 404 | malformed (valid HTTP, wrong JSON shape) | empty (valid HTTP, no results)."""

    def __init__(self, routes: dict | None = None, fail: str | None = None) -> None:
        self.routes, self.fail, self.calls = routes or {}, fail, []

    async def get(self, url, params=None, headers=None):
        self.calls.append((url, params))
        request = httpx.Request("GET", url)
        if self.fail == "slow":                             # a hung upstream: never answers in time
            await asyncio.sleep(30)
        if self.fail == "connect":
            raise httpx.ConnectError("connection refused", request=request)
        if self.fail == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if self.fail in ("500", "404"):
            return httpx.Response(int(self.fail), request=request, text="upstream says no")
        if self.fail == "malformed":
            return httpx.Response(200, request=request, json={"unexpected": ["shape"]})
        if self.fail == "empty":
            return httpx.Response(200, request=request, json={"results": [], "items": [], "docs": [], "matches": [], "data": []})
        for fragment, body in self.routes.items():
            if fragment in url:
                status, payload = body if isinstance(body, tuple) else (200, body)
                if callable(payload):                       # a route can compute its body from the request
                    payload = payload(url, params)
                if isinstance(payload, str):
                    return httpx.Response(status, request=request, text=payload)
                return httpx.Response(status, request=request, json=payload)
        raise httpx.ConnectError(f"no fake route for {url}", request=request)


def make_bot(routes=None, fail=None, clock=None, registry: Registry | None = None) -> tuple[Bot, FakeHttp]:
    reg, http = registry or real_registry(), FakeHttp(routes, fail)
    store = ContextStore(clock) if clock else ContextStore()
    return Bot(reg, Dispatcher(reg), decide, store, SimpleNamespace(http=http)), http


# --- reply linter: structural problems that make a reply look broken, whatever the content ------------------------------
BAD_PATTERNS = {
    "python leak": re.compile(r"Traceback|\bNone\b|\bnan\b|<function|<coroutine|Decision\(|\bNoneType\b|object at 0x|KeyError|TypeError"),
    "unfilled placeholder": re.compile(r"\{[a-z_]+\}"),
    "raw html": re.compile(r"</?(?:a|b|i|u|p|br|div|span|ul|ol|li|font|strong|em|table|tr|td|h[1-6]|img|script|style)\b[^>]*>|&nbsp;|&amp;|&quot;|&#\d+;"),
    "markdown that WhatsApp doesn't render": re.compile(r"\*\*|^#{1,6} |\[[^\]]+\]\(https?://"),
}
MAX_REPLY = 4000


def lint_reply(reply) -> list[str]:
    """Problems found in a reply (empty list = clean)."""
    if not isinstance(reply, str):
        return [f"reply is {type(reply).__name__}, not str"]
    problems = []
    if not reply.strip():
        problems.append("empty reply")
    if len(reply) > MAX_REPLY:
        problems.append(f"reply is {len(reply)} chars (max {MAX_REPLY})")
    if reply != reply.strip("\n") or "\n\n\n" in reply:
        problems.append("stray blank lines")
    if any(line != line.rstrip() for line in reply.split("\n")):
        problems.append("trailing spaces")
    for name, pat in BAD_PATTERNS.items():
        if m := pat.search(reply):
            problems.append(f"{name}: {m.group(0)!r}")
    return problems
