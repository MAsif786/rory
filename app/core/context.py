"""Per-chat memory: active game, last turn (for follow-ups) and a pending question. All expire."""
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable

from app.intent.decision import LastTurn

SESSION_TTL = 10 * 60
TURN_TTL = 5 * 60
REPEAT_TTL = 60


@dataclass
class ActiveSession:
    tool: str
    state: Any


@dataclass
class Pending:
    feature: str
    args: dict
    missing: list[str]


@dataclass
class Repeat:
    """The chat's last message and what we answered, to notice when it is sent again."""
    text: str
    feature: str | None            # None: nothing matched
    reply: str | None
    count: int = 1


@dataclass
class ChatContext:
    session: ActiveSession | None = None
    last_turn: LastTurn | None = None
    pending: Pending | None = None
    repeat: Repeat | None = None
    repeat_at: float = 0
    session_at: float = 0
    turn_at: float = 0
    pending_at: float = 0
    last_seen: float = 0


class ContextStore:
    """Per-chat state, bounded: chats idle for `idle_ttl` seconds are forgotten, and past `max_chats` the least recently used go first.
    Ordering by recency (OrderedDict) makes both cleanups cheap: they only ever look at the oldest end."""

    SWEEP_EVERY = 200                   # lookups between idle sweeps

    def __init__(self, clock: Callable[[], float] = time.monotonic, idle_ttl: float = 3600, max_chats: int = 10_000) -> None:
        self.clock, self.idle_ttl, self.max_chats = clock, idle_ttl, max_chats
        self._chats: OrderedDict[str, ChatContext] = OrderedDict()
        self._lookups = 0

    def __len__(self) -> int:
        return len(self._chats)

    def _evict(self, now: float) -> None:
        while len(self._chats) > self.max_chats:
            self._chats.popitem(last=False)
        if self._lookups % self.SWEEP_EVERY == 0:
            while self._chats and now - next(iter(self._chats.values())).last_seen > self.idle_ttl:
                self._chats.popitem(last=False)

    def get(self, chat_id: str) -> ChatContext:
        now = self.clock()
        self._lookups += 1
        c = self._chats.get(chat_id)
        if c is None or now - c.last_seen > self.idle_ttl:           # new chat, or one that has gone cold
            c = self._chats[chat_id] = ChatContext()
        c.last_seen = now
        self._chats.move_to_end(chat_id)
        self._evict(now)
        if c.session and now - c.session_at > SESSION_TTL:
            c.session = None
        if c.last_turn and now - c.turn_at > TURN_TTL:
            c.last_turn = None
        if c.pending and now - c.pending_at > TURN_TTL:
            c.pending = None
        if c.repeat and now - c.repeat_at > REPEAT_TTL:
            c.repeat = None
        return c

    def set_repeat(self, chat_id: str, repeat: Repeat | None) -> None:
        c = self.get(chat_id)
        c.repeat, c.repeat_at = repeat, self.clock()

    def set_session(self, chat_id: str, session: ActiveSession | None) -> None:
        c = self.get(chat_id)
        c.session, c.session_at = session, self.clock()

    def set_last_turn(self, chat_id: str, turn: LastTurn | None) -> None:
        c = self.get(chat_id)
        c.last_turn, c.turn_at = turn, self.clock()

    def set_pending(self, chat_id: str, pending: Pending | None) -> None:
        c = self.get(chat_id)
        c.pending, c.pending_at = pending, self.clock()
