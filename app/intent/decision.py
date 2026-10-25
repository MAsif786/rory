"""The one result an intent engine returns, and the one-function engine interface."""
from dataclasses import dataclass, field
from typing import Callable, Literal

from app.core.schemas import FeatureSpec


@dataclass
class LastTurn:
    feature: str                    # full name, e.g. "weather.current"
    args: dict


@dataclass
class Decision:
    kind: Literal["match", "followup", "clarify", "none"]
    feature: str | None = None
    args: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)   # clarify: inputs still needed
    question: str = ""                                 # clarify: what to ask
    via: str = ""                                      # how it was understood beyond a direct match: "date", "maths", "synonym"
    entities: dict = field(default_factory=dict)       # extracted entities, e.g. {"when": "tomorrow"}


# An engine is just: (text, feature metadata, last turn) -> Decision. It never sees handlers.
IntentEngine = Callable[[str, list[FeatureSpec], LastTurn | None], Decision]
