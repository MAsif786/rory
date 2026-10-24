"""What happened to the current message, for structured logs: the router fills it in, the webhook logs it.
A ContextVar is per async task, so concurrent chats never see each other's trace."""
from contextvars import ContextVar

_current: ContextVar[dict | None] = ContextVar("rory_trace", default=None)


def start() -> dict:
    t: dict = {}
    _current.set(t)
    return t


def note(**fields) -> None:
    t = _current.get()
    if t is not None:
        t.update(fields)


def current() -> dict:
    return _current.get() or {}
