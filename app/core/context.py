"""Per-chat memory: active game, last turn (for follow-ups) and a pending question. All expire."""
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.intent.decision import LastTurn

SESSION_TTL = 10 * 60
TURN_TTL = 5 * 60


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
class ChatContext:
    session: ActiveSession | None = None
    last_turn: LastTurn | None = None
    pending: Pending | None = None
    session_at: float = 0
    turn_at: float = 0
    pending_at: float = 0


class ContextStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock, self._chats = clock, {}

    def get(self, chat_id: str) -> ChatContext:
        c = self._chats.setdefault(chat_id, ChatContext())
        now = self.clock()
        if c.session and now - c.session_at > SESSION_TTL:
            c.session = None
        if c.last_turn and now - c.turn_at > TURN_TTL:
            c.last_turn = None
        if c.pending and now - c.pending_at > TURN_TTL:
            c.pending = None
        return c

    def set_session(self, chat_id: str, session: ActiveSession | None) -> None:
        c = self.get(chat_id)
        c.session, c.session_at = session, self.clock()

    def set_last_turn(self, chat_id: str, turn: LastTurn | None) -> None:
        c = self.get(chat_id)
        c.last_turn, c.turn_at = turn, self.clock()

    def set_pending(self, chat_id: str, pending: Pending | None) -> None:
        c = self.get(chat_id)
        c.pending, c.pending_at = pending, self.clock()
