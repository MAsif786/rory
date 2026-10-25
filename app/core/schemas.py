"""Plain data shapes shared by tools, the registry, the dispatcher and the intent engines."""
from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field


class Schema(BaseModel):
    """Base for declarative metadata: immutable, and typos in field names fail loudly."""
    model_config = ConfigDict(frozen=True, extra="forbid")


class Input(Schema):
    type: Literal["text", "int", "float"] = "text"
    required: bool = False
    default: Any = None
    choices: tuple | None = None
    ask: str | None = None             # question to ask when this input is missing (default: "Which <name>?")
    pattern: str | None = None         # regex a phrase placeholder must match, e.g. r"\d+(?:\.\d+)?" (default: any text)


class Followup(Schema):
    phrases: list[str]
    overrides: list[str] = []          # args taken from the phrase's {placeholders}
    sets: dict[str, Any] = {}          # args forced to a fixed value


# A ready-made follow-up for answers that are random or can be repeated: "again" / "one more" re-run the last request with the same arguments.
# Use it on coin flips, dice, picks, jokes, facts:  @tool.feature(..., followups=[AGAIN])
AGAIN = Followup(phrases=["again", "once more", "one more", "one more time", "another", "another one", "more", "next", "do it again", "go again",
                          "again please", "repeat", "repeat that", "one more please"])


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
class FeatureSpec(Schema):
    tool: str
    name: str                      # short name, e.g. "current"
    description: str = ""
    kind: Literal["answer", "session"] = "answer"
    phrases: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    negatives: tuple[str, ...] = ()
    inputs: dict[str, Input] = Field(default_factory=dict)
    followups: tuple[Followup, ...] = ()
    repeat: Literal["rerun", "reuse"] = "rerun"   # asked again within a minute: run again, or reuse the last answer (lookups)
    synonyms: tuple[tuple[str, str], ...] = ()    # (word people use, word this tool's phrases use): see app/nlu/lexicon.py

    @property
    def full_name(self) -> str:
        return f"{self.tool}.{self.name}"


@dataclass
class Context:
    """Passed to every handler as `ctx`."""
    chat_id: str
    text: str
    services: Any
    now: float = 0.0          # seconds on the bot's clock (monotonic): tools use this for "how long ago", never their own clock, so time is testable


class UserError(Exception):
    """Raise from a handler when the message is safe to show the user (e.g. "couldn't find that city")."""


Handler = Callable[..., Any]
