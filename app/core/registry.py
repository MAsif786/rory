"""Finds tools in tools/<name>/tool.py and rejects bad ones. A bad tool never stops the rest loading."""
import importlib
import inspect
import logging
import re
from pathlib import Path

from app.core.schemas import FeatureSpec, Handler
from app.core.tool import Tool

log = logging.getLogger("wa-bot.registry")
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _shape(phrase: str, inputs: dict) -> str:
    """The phrase with each placeholder replaced by its pattern, so `{n} km` and `{name} km` clash but `{n:digits}` doesn't."""
    def slot(m):
        inp = inputs.get(m.group(1))
        return "{" + (inp.pattern if inp and inp.pattern else "") + "}"
    return " ".join(_PLACEHOLDER.sub(slot, phrase).lower().split())


class Registry:
    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}
        self.rejected: dict[str, str] = {}          # folder -> why it was rejected
        self._phrases: dict[str, str] = {}          # phrase shape -> feature that owns it

    # --- discovery -------------------------------------------------------------------------
    def discover(self, path: Path | str = "tools", package: str = "tools") -> "Registry":
        for folder in sorted(Path(path).iterdir()):
            if not folder.is_dir() or folder.name.startswith(("_", ".")) or not (folder / "tool.py").exists():
                continue
            try:
                module = importlib.import_module(f"{package}.{folder.name}.tool")
                self.add(getattr(module, "tool", None), folder.name)
            except Exception as e:                  # noqa: BLE001 - any failure rejects only this tool
                self._reject(folder.name, f"{type(e).__name__}: {e}")
        return self

    def add(self, tool: Tool | None, folder: str) -> None:
        try:
            if not isinstance(tool, Tool):
                raise ValueError("tool.py must define `tool = Tool(...)`")
            shapes = self._validate(tool, folder)
        except ValueError as e:
            return self._reject(folder, str(e))
        self.tools[tool.name] = tool
        self._phrases.update(shapes)
        log.info("loaded tool %s (%d features)", tool.name, len(tool.features))

    def _reject(self, folder: str, why: str) -> None:
        self.rejected[folder] = why
        log.error("rejected tool %r: %s", folder, why)

    # --- validation ------------------------------------------------------------------------
    def _validate(self, tool: Tool, folder: str) -> dict[str, str]:
        if tool.name != folder:
            raise ValueError(f"folder name {folder!r} must equal tool name {tool.name!r}")
        if tool.name in self.tools:
            raise ValueError(f"duplicate tool name {tool.name!r}")
        if not tool.features:
            raise ValueError("needs at least one @tool.feature")
        shapes: dict[str, str] = {}
        has_session = False
        for feat in tool.features.values():
            spec, where = feat.spec, f"feature {feat.spec.name!r}"
            if not (spec.phrases or spec.keywords):
                raise ValueError(f"{where}: needs phrases or keywords")
            if not spec.examples:
                raise ValueError(f"{where}: needs at least one example")
            if not inspect.iscoroutinefunction(feat.handler):
                raise ValueError(f"{where}: handler must be `async def`")
            self._check_params(feat.handler, spec, where)
            for name, inp in spec.inputs.items():
                try:
                    re.compile(inp.pattern or "")
                except re.error as e:
                    raise ValueError(f"{where}: input {name!r} has a bad pattern: {e}") from None
            for phrase in spec.phrases:
                self._check_placeholders(phrase, spec, where)
                shape = _shape(phrase, spec.inputs)
                owner = shapes.get(shape) or self._phrases.get(shape)
                if owner and owner != spec.full_name:
                    raise ValueError(f"{where}: phrase {phrase!r} is already claimed by {owner}")
                shapes[shape] = spec.full_name
            for fu in spec.followups:
                for ph in fu.phrases:
                    self._check_placeholders(ph, spec, f"{where} follow-up")
                for arg in [*fu.overrides, *fu.sets]:
                    if arg not in spec.inputs:
                        raise ValueError(f"{where}: follow-up refers to unknown input {arg!r}")
            has_session |= spec.kind == "session"
        if has_session != (tool.session_handler is not None):
            raise ValueError("a session feature and a @tool.session handler must come together")
        if tool.session_handler and not inspect.iscoroutinefunction(tool.session_handler):
            raise ValueError("session handler must be `async def`")
        return shapes

    @staticmethod
    def _check_placeholders(phrase: str, spec: FeatureSpec, where: str) -> None:
        for name in _PLACEHOLDER.findall(phrase):
            if name not in spec.inputs:
                raise ValueError(f"{where}: {{{name}}} in {phrase!r} has no matching input")

    @staticmethod
    def _check_params(handler: Handler, spec: FeatureSpec, where: str) -> None:
        params = list(inspect.signature(handler).parameters.values())
        if not params or params[0].name != "ctx":
            raise ValueError(f"{where}: handler's first argument must be `ctx`")
        names = {p.name for p in params[1:] if p.kind is not p.VAR_KEYWORD}
        if names != set(spec.inputs):
            raise ValueError(f"{where}: handler args {sorted(names)} must match inputs {sorted(spec.inputs)}")

    # --- lookups ---------------------------------------------------------------------------
    def specs(self) -> list[FeatureSpec]:
        """Metadata only - what intent engines get to see."""
        return [f.spec for t in self.tools.values() for f in t.features.values()]

    def spec(self, full_name: str) -> FeatureSpec | None:
        tool, _, name = full_name.partition(".")
        feat = self.tools.get(tool, None) and self.tools[tool].features.get(name)
        return feat.spec if feat else None
