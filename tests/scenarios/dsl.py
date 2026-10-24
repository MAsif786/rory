"""A tiny DSL for conversation tests. A scenario is a list of turns; every reply is also linted for structural problems.

    Scenario("switch city", [
        T("weather in lahore", has="Lahore"),
        T("what about karachi", http="Karachi"),          # the last upstream call mentioned Karachi
    ])

T(say, ...) checks, all optional:  has / lacks (substrings, str or list)  eq (exact)  rx (regex)  any_of (one of several substrings)
                                   http (substring of any upstream call made this turn)  no_http (no upstream call was made this turn)
                                   session (tool name expected active after the turn, or None for "no game")  wait (seconds to advance first)
                                   fail (set/clear a simulated outage: "connect", "timeout", "500", ... or None)  pre (fn(bot) to tweak internals)
"""
import re
from dataclasses import dataclass, field
from typing import Callable

from tests.helpers import lint_reply

UNSET = object()


@dataclass
class T:
    say: str
    has: str | list = ()
    lacks: str | list = ()
    eq: str | None = None
    rx: str | None = None
    any_of: list = ()
    http: str | None = None
    no_http: bool = False
    session: object = UNSET
    wait: float = 0
    fail: object = UNSET
    pre: Callable | None = None
    lint: bool = True


@dataclass
class Scenario:
    name: str
    turns: list
    env: dict = field(default_factory=dict)
    tags: tuple = ()

    def __repr__(self) -> str:
        return self.name


def _as_list(x):
    return [x] if isinstance(x, str) else list(x)


async def play(scenario: Scenario, bot, http, clock) -> None:
    for n, t in enumerate(scenario.turns, 1):
        where = f"[{scenario.name}] turn {n} {t.say!r}"
        if t.wait:
            clock.t += t.wait
        if t.fail is not UNSET:
            http.fail = t.fail
        if t.pre:
            t.pre(bot)
        before = len(http.calls)
        reply = await bot.respond("chat", t.say)
        if t.lint:
            assert not (problems := lint_reply(reply)), f"{where}: reply is malformed: {problems}\n{reply}"
        for s in _as_list(t.has):
            assert s in reply, f"{where}: expected {s!r} in reply:\n{reply}"
        for s in _as_list(t.lacks):
            assert s not in reply, f"{where}: did not expect {s!r} in reply:\n{reply}"
        if t.eq is not None:
            assert reply == t.eq, f"{where}: expected exactly {t.eq!r}, got:\n{reply}"
        if t.rx:
            assert re.search(t.rx, reply, re.S), f"{where}: /{t.rx}/ did not match:\n{reply}"
        if t.any_of:
            assert any(s in reply for s in t.any_of), f"{where}: expected one of {list(t.any_of)} in reply:\n{reply}"
        if t.http:
            assert any(t.http.lower() in str(c).lower() for c in http.calls[before:]), f"{where}: no upstream call this turn mentioned {t.http!r}: {http.calls[before:]!r}"
        if t.no_http:
            assert len(http.calls) == before, f"{where}: made an upstream call, expected none: {http.calls[before:]!r}"
        if t.session is not UNSET:
            active = bot.store.get("chat").session
            assert (active.tool if active else None) == t.session, f"{where}: active game is {active.tool if active else None!r}, expected {t.session!r}"
