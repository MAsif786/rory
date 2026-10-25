"""Shared pieces for game tools. A game is a small class (the session state); `game_tool()` turns it into a Tool.

A game class has `start()` and `handle(text)` (either may be async) and a `finished` property. `handle` returns "" when a
message isn't for the game, which becomes PassThrough so routing tries the next step. `quit`/`stop` are handled by routing.
"""
import inspect
from abc import ABC, abstractmethod

from app.core.schemas import Continue, Finish, PassThrough, SessionStart
from app.core.tool import Tool


class Game(ABC):
    """One instance per chat per running game; it is the session state."""

    key: str = ""                          # tool name, and the word in "play <key>"
    title: str = ""
    description: str = ""
    aliases: tuple[str, ...] = ()          # other names people use to start it
    ambiguous_aliases: tuple[str, ...] = ()   # ordinary words ("memory", "guess"): only count after "play ..."

    # set by the adapter before each call
    sender: str = ""
    sender_id: str = ""
    group_chat: bool = False
    ctx = None

    @abstractmethod
    def start(self) -> str: ...

    @abstractmethod
    def handle(self, text: str) -> str: ...

    @property
    def finished(self) -> bool:
        return False


async def _call(fn, *args):
    out = fn(*args)
    return await out if inspect.isawaitable(out) else out


def _bind(game: Game, ctx) -> None:
    game.ctx, game.sender_id = ctx, ctx.chat_id


def game_tool(cls: type[Game], *, emoji: str = "🎮") -> Tool:
    names = {cls.key, cls.title.lower(), *(a.lower() for a in cls.aliases)}
    ambiguous = {a.lower() for a in cls.ambiguous_aliases}
    phrases = [p for n in sorted(names) for p in (f"play {n}", f"let's play {n}", f"lets play {n}", f"start {n}", f"play a game of {n}")]
    phrases += [n for n in sorted(names) if n not in ambiguous]
    phrases = list(dict.fromkeys(phrases))
    tool = Tool(cls.key, title=cls.title, emoji=emoji, description=cls.description, category="games")

    @tool.feature("start", kind="session", description=f"Play {cls.title}", phrases=phrases,
                  examples=[f"play {cls.key}"])
    async def start(ctx):
        game = cls()
        _bind(game, ctx)
        return SessionStart(game, await _call(game.start))

    @tool.session
    async def on_message(ctx, state, message):
        _bind(state, ctx)
        reply = await _call(state.handle, message)
        if not reply:
            return PassThrough()
        return Finish(reply) if state.finished else Continue(state, reply)

    return tool
