"""The only place tool code runs: validates args, applies a timeout, hides errors behind a generic message."""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.registry import Registry
from app.core.schemas import Context, Continue, Finish, Input, PassThrough, SessionStart, UserError

log = logging.getLogger("wa-bot.dispatcher")
GENERIC_ERROR = "😕 Something went wrong. Please try again."


class BadArgs(Exception):
    """Raised for user-facing validation problems; the message is safe to show."""


@dataclass
class Run:
    reply: str | None = None
    ok: bool = True
    args: dict = field(default_factory=dict)
    session: SessionStart | None = None


class Dispatcher:
    def __init__(self, registry: Registry, timeout: float = 15.0) -> None:
        self.registry, self.timeout = registry, timeout

    async def run_feature(self, full_name: str, args: dict, ctx: Context) -> Run:
        tool_name, _, name = full_name.partition(".")
        feat = self.registry.tools.get(tool_name) and self.registry.tools[tool_name].features.get(name)
        if not feat:
            return Run(GENERIC_ERROR, ok=False)
        try:
            clean = self._validate(feat.spec.inputs, args)
        except BadArgs as e:
            return Run(str(e), ok=False)
        out = await self._call(feat.handler(ctx, **clean))
        if out is None:
            return Run(GENERIC_ERROR, ok=False)
        if isinstance(out, UserError):
            return Run(str(out), ok=False)
        if isinstance(out, SessionStart):
            return Run(out.reply, args=clean, session=out)
        return Run(str(out), args=clean)

    async def run_session(self, tool_name: str, state: Any, message: str, ctx: Context):
        """Returns Continue, Finish or PassThrough."""
        tool = self.registry.tools.get(tool_name)
        out = await self._call(tool.session_handler(ctx, state, message)) if tool and tool.session_handler else None
        if isinstance(out, UserError):
            return Finish(str(out))
        return out if isinstance(out, (Continue, Finish, PassThrough)) else Finish(GENERIC_ERROR)

    async def _call(self, coro):
        try:
            return await asyncio.wait_for(coro, self.timeout)
        except UserError as e:                               # safe to show
            return e
        except Exception:                                    # noqa: BLE001 - details go to the log only
            log.exception("tool handler failed")
            return None

    @staticmethod
    def _validate(inputs: dict[str, Input], args: dict) -> dict:
        unknown = set(args) - set(inputs)
        if unknown:
            raise BadArgs(f"Unknown argument: {', '.join(sorted(unknown))}")
        clean = {}
        for name, spec in inputs.items():
            value = args.get(name)
            if value in (None, ""):
                if spec.required:
                    raise BadArgs(f"Please tell me the {name}.")
                clean[name] = spec.default
                continue
            try:
                value = {"text": str, "int": int, "float": float}[spec.type](value)
            except ValueError:
                raise BadArgs(f"{name} must be a {spec.type}.") from None
            if spec.choices and value not in spec.choices:
                raise BadArgs(f"{name} must be one of: {', '.join(map(str, spec.choices))}.")
            clean[name] = value
        return clean
