"""Plain data shapes shared by tools, the registry, the dispatcher and the intent engines."""
from dataclasses import dataclass, field
from typing import Any, Callable, Literal


@dataclass(frozen=True)
class Input:
    type: Literal["text", "int", "float"] = "text"
    required: bool = False
    default: Any = None
    choices: tuple | None = None


@dataclass(frozen=True)
class Followup:
    phrases: list[str]
    overrides: list[str] = field(default_factory=list)   # args taken from the phrase's {placeholders}
    sets: dict[str, Any] = field(default_factory=dict)   # args forced to a fixed value


# --- what a game handler returns -------------------------------------------------------------
@dataclass
class SessionStart:
    state: Any
    reply: str


@dataclass
class Continue:
    state: Any
    reply: str


@dataclass
class Finish:
    reply: str


class PassThrough:
    """The message isn't for the game: let routing try the next step."""


# --- metadata only: this is all an intent engine ever sees -----------------------------------
@dataclass(frozen=True)
class FeatureSpec:
    tool: str
    name: str                      # short name, e.g. "current"
    description: str = ""
    kind: Literal["answer", "session"] = "answer"
    phrases: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    negatives: tuple[str, ...] = ()
    inputs: dict[str, Input] = field(default_factory=dict)
    followups: tuple[Followup, ...] = ()

    @property
    def full_name(self) -> str:
        return f"{self.tool}.{self.name}"


@dataclass
class Context:
    """Passed to every handler as `ctx`."""
    chat_id: str
    text: str
    services: Any


class UserError(Exception):
    """Raise from a handler when the message is safe to show the user (e.g. "couldn't find that city")."""


Handler = Callable[..., Any]
