"""Routing: one fixed order. Reads Decision and results only - it imports no NLU code."""
import asyncio
import logging
import sys
from concurrent.futures import ThreadPoolExecutor

from app import replies
from app import inbox, trace
from app.format import tidy
from app.core.context import ActiveSession, ContextStore, Pending, Repeat
from app.core.dispatcher import GENERIC_ERROR, NETWORK_ERROR, Dispatcher
from app.core.registry import Registry
from app.core.schemas import Context, Continue, Finish, PassThrough
from app.intent.decision import Decision, IntentEngine, LastTurn

# ONE thread for the engine: with several CPU-bound threads the event-loop thread (which sends the webhook acknowledgements) waits
# behind all of them for the GIL; with one, the loop gets the GIL back every switch interval and stays responsive.
_ENGINE_THREAD = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rory-engine")
sys.setswitchinterval(0.001)                  # hand the GIL over every 1 ms instead of 5 ms: acknowledgements are tiny and want it often
log = logging.getLogger("wa-bot.unmatched")
STOP_WORDS = {"stop", "quit", "exit"}
MENU_WORDS = {"menu", "home", "start"}
GAME_WORDS = {"games", "game list", "list games", "play games", "play a game", "play something", "bored", "i'm bored", "im bored", "i am bored"}


class Bot:
    def __init__(self, registry: Registry, dispatcher: Dispatcher, engine: IntentEngine,
                 store: ContextStore, services=None, recorder=None) -> None:
        self.registry, self.dispatcher, self.engine, self.store, self.services = registry, dispatcher, engine, store, services
        self.recorder = recorder                      # optional improvement inbox (app/inbox.py)

    async def handle(self, chat_id: str, text: str) -> str | None:
        """Returns the reply, or None when nothing matched (caller decides the fallback)."""
        word = text.strip().lower()
        command = word.lstrip("!/")
        ctx, chat = Context(chat_id, text, self.services), self.store.get(chat_id)

        # 0. menu and help always work, even mid-game (the game stays active)
        if command in MENU_WORDS or command == "help" or command.startswith("help "):
            trace.note(kind="help", feature=None)
            return replies.home_menu(self.registry) if command in MENU_WORDS else replies.help_for(self.registry, command[4:])

        if " ".join(command.rstrip(".!?").split()) in GAME_WORDS:
            trace.note(kind="help", feature=None)
            return replies.games_menu(self.registry)

        # 1. active game (stop/quit always ends it)
        if chat.session:
            if word in STOP_WORDS:
                self.store.set_session(chat_id, None)
                return "Game ended."
            trace.note(kind="game", feature=f"{chat.session.tool}.session")
            out = await self.dispatcher.run_session(chat.session.tool, chat.session.state, text, ctx)
            if isinstance(out, Continue):
                self.store.set_session(chat_id, ActiveSession(chat.session.tool, out.state))
                return out.reply
            if isinstance(out, Finish):
                self.store.set_session(chat_id, None)
                return out.reply
            assert isinstance(out, PassThrough)

        # 2. direct commands
        if command == "ping":
            trace.note(kind="command", feature=None)
            return "pong 🏓"

        # 3. the bot asked a question: this message is the answer, unless it is clearly a different request
        if chat.pending:
            p = chat.pending
            self.store.set_pending(chat_id, None)
            other = await self._decide(text, None)
            if not (other.kind == "match" and other.feature != p.feature):
                return await self._run(chat_id, p.feature, {**p.args, p.missing[0]: text.strip()}, ctx)
            chat = self.store.get(chat_id)                  # fall through: handle it as a fresh request

        # 4. intent engine
        key, last = " ".join(word.rstrip(".!?؟ ").split()), chat.repeat
        again = last if last and last.text == key else None          # the same message, sent again within a minute
        d: Decision = await self._decide(text, chat.last_turn)
        if d.kind in ("match", "followup"):
            spec = self.registry.spec(d.feature)
            if again and again.feature == d.feature and again.reply and spec and spec.repeat == "reuse":
                self.store.set_repeat(chat_id, Repeat(key, d.feature, again.reply, again.count + 1))
                trace.note(kind="repeat", feature=d.feature)
                return replies.repeated(again.reply, again.count + 1)
            return await self._run(chat_id, d.feature, d.args, ctx, key, again)
        if d.kind == "clarify":
            self.store.set_pending(chat_id, Pending(d.feature, d.args, d.missing))
            trace.note(kind="clarify", feature=d.feature)
            return d.question
        self.store.set_repeat(chat_id, Repeat(key, None, None, again.count + 1 if again else 1))
        return None

    async def _decide(self, text: str, last) -> Decision:
        """The engine is plain CPU-bound Python (1-10 ms). Run it in a worker thread: the GIL still serialises the work, but the event loop
        gets a turn every few ms, so a burst of messages cannot delay the webhook's acknowledgements or the other chats' I/O."""
        return await asyncio.get_running_loop().run_in_executor(_ENGINE_THREAD, self.engine, text, self.registry.specs(), last)

    async def respond(self, chat_id: str, text: str) -> str:
        """handle(), plus a fallback for messages nothing understood (which changes if it is repeated)."""
        reply = await self.handle(chat_id, text)
        if not reply:
            last = self.store.get(chat_id).repeat
            result = replies.classify_unmatched(self.registry, last.count if last else 1, text)
            reply = result.reply
            trace.note(kind="fallback" if result.kind == "unmatched" else "out_of_scope", feature=result.category)
            log.info("%s: %r", result.kind, text[:200])          # scripts/quality_report.py --log reads these to find what to teach the bot
            if self.recorder:
                if result.kind == "out_of_scope":                # understood but not offered: filed by capability so demand can be counted
                    self.recorder.record("out_of_scope", text, chat_id, feature=result.category)
                else:
                    near = inbox.nearest_example(text, self.registry.specs())
                    self.recorder.record("unmatched", text, chat_id, nearest=near[0] if near else None, feature=near[1] if near else None)
        return tidy(reply)

    async def _run(self, chat_id: str, feature: str, args: dict, ctx: Context,
                   key: str = "", again: Repeat | None = None) -> str:
        run = await self.dispatcher.run_feature(feature, args, ctx)
        trace.note(kind="answer" if run.ok else "error", feature=feature)
        if self.recorder and not run.ok and run.reply in (GENERIC_ERROR, NETWORK_ERROR):   # the tool failed, not the user's input
            self.recorder.record("tool_error", ctx.text, ctx.chat_id, feature=feature, note="network" if run.reply == NETWORK_ERROR else "internal")
        if run.ok and run.session:
            tool = feature.partition(".")[0]
            self.store.set_session(chat_id, ActiveSession(tool, run.session.state))
        elif run.ok:
            self.store.set_last_turn(chat_id, LastTurn(feature, run.args))
            if key:
                count = again.count + 1 if again and again.feature == feature else 1
                self.store.set_repeat(chat_id, Repeat(key, feature, run.reply, count))
        return run.reply
