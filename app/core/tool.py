"""The Tool class: one standard way to declare a tool."""
from dataclasses import dataclass
from typing import Callable, Literal

from app.core.schemas import FeatureSpec, Followup, Handler, Input


@dataclass
class Feature:
    spec: FeatureSpec
    handler: Handler


class Tool:
    def __init__(self, name: str, *, title: str = "", emoji: str = "🧩", description: str = "", synonyms: dict[str, str] | None = None) -> None:
        self.name = name
        self.synonyms = {k.lower(): v.lower() for k, v in (synonyms or {}).items()}   # {"gag": "joke"}: words people use -> words our phrases use
        self.title, self.emoji, self.description = title or name.replace("_", " ").title(), emoji, description      # shown in help/menu
        self.features: dict[str, Feature] = {}
        self.session_handler: Handler | None = None

    def feature(self, name: str, *, description: str = "", kind: Literal["answer", "session"] = "answer",
                phrases: list[str] = (), keywords: list[str] = (), examples: list[str] = (),
                negatives: list[str] = (), inputs: dict[str, Input] | None = None,
                followups: list[Followup] = (), repeat: Literal["rerun", "reuse"] = "rerun") -> Callable[[Handler], Handler]:
        def register(fn: Handler) -> Handler:
            spec = FeatureSpec(tool=self.name, name=name, description=description, kind=kind, phrases=tuple(phrases),
                               keywords=tuple(keywords), examples=tuple(examples), negatives=tuple(negatives),
                               inputs=dict(inputs or {}), followups=tuple(followups), repeat=repeat,
                               synonyms=tuple(sorted(self.synonyms.items())))
            self.features[name] = Feature(spec, fn)
            return fn
        return register

    def session(self, fn: Handler) -> Handler:
        self.session_handler = fn
        return fn
