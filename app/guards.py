"""Small protections around the bot: rate limiting, duplicate-message detection and per-chat ordering."""
import asyncio
import time
from collections import OrderedDict, deque
from typing import Callable, Literal

Verdict = Literal["ok", "notify", "drop"]


class RateLimiter:
    """Sliding window per sender. Over the limit the first blocked message gets a notice ("notify"), the rest are dropped silently,
    so a spammer cannot make the bot spam back."""

    def __init__(self, max_events: int, window: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.max, self.window, self.clock = max_events, window, clock
        self._hits: dict[str, deque] = {}
        self._notified: dict[str, float] = {}

    def check(self, key: str) -> Verdict:
        now = self.clock()
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] > self.window:
            q.popleft()
        if len(self._hits) > 5000:                                 # keep memory bounded
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                self._hits.pop(k, None)
                self._notified.pop(k, None)
        if len(q) < self.max:
            q.append(now)
            self._notified.pop(key, None)
            return "ok"
        if key not in self._notified or now - self._notified[key] > self.window:
            self._notified[key] = now
            return "notify"
        return "drop"


class Seen:
    """Remembers message ids for a short time, so a retried or doubled webhook is answered once."""

    def __init__(self, ttl: float, maxsize: int = 50_000, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl, self.maxsize, self.clock = ttl, maxsize, clock
        self._ids: OrderedDict[str, float] = OrderedDict()

    def duplicate(self, message_id: str | None) -> bool:
        """True if this id was seen within the TTL. Records it otherwise. A missing id is never a duplicate."""
        if not message_id:
            return False
        now = self.clock()
        while self._ids and (now - next(iter(self._ids.values())) > self.ttl or len(self._ids) >= self.maxsize):
            self._ids.popitem(last=False)
        if message_id in self._ids and now - self._ids[message_id] <= self.ttl:
            return True
        self._ids[message_id] = now
        return False


class KeyedLocks:
    """One lock per key, created on demand and removed when nobody uses it. Messages of one chat are processed strictly in order
    (a "weather" followed by "lahore" must not race), while different chats run in parallel."""

    def __init__(self) -> None:
        self._locks: dict[str, list] = {}

    def __call__(self, key: str) -> "_Held":
        return _Held(self, key)


class _Held:
    def __init__(self, owner: KeyedLocks, key: str) -> None:
        self.owner, self.key = owner, key

    async def __aenter__(self):
        entry = self.owner._locks.setdefault(self.key, [asyncio.Lock(), 0])
        entry[1] += 1
        await entry[0].acquire()

    async def __aexit__(self, *exc):
        entry = self.owner._locks[self.key]
        entry[0].release()
        entry[1] -= 1
        if entry[1] == 0:
            del self.owner._locks[self.key]
