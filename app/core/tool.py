"""The Tool class: one standard way to declare a tool."""
from dataclasses import dataclass
from typing import Callable, Literal

from app.core.schemas import FeatureSpec, Followup, Handler, Input


@dataclass
class Feature:
    spec: FeatureSpec
    handler: Handler


class Tool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.features: dict[str, Feature] = {}
        self.session_handler: Handler | None = None

    def feature(self, name: str, *, description: str = "", kind: Literal["answer", "session"] = "answer",
                phrases: list[str] = (), keywords: list[str] = (), examples: list[str] = (),
                negatives: list[str] = (), inputs: dict[str, Input] | None = None,
                followups: list[Followup] = ()) -> Callable[[Handler], Handler]:
        def register(fn: Handler) -> Handler:
            spec = FeatureSpec(self.name, name, description, kind, tuple(phrases), tuple(keywords),
                               tuple(examples), tuple(negatives), dict(inputs or {}), tuple(followups))
            self.features[name] = Feature(spec, fn)
            return fn
        return register

    def session(self, fn: Handler) -> Handler:
        self.session_handler = fn
        return fn
