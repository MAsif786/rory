"""Routing: one fixed order. Reads Decision and results only - it imports no NLU code."""
from app import replies
from app.core.context import ActiveSession, ContextStore, Pending, Repeat
from app.core.dispatcher import Dispatcher
from app.core.registry import Registry
from app.core.schemas import Context, Continue, Finish, PassThrough
from app.intent.decision import Decision, IntentEngine, LastTurn

STOP_WORDS = {"stop", "quit", "exit"}
MENU_WORDS = {"menu", "home", "start"}


class Bot:
    def __init__(self, registry: Registry, dispatcher: Dispatcher, engine: IntentEngine,
                 store: ContextStore, services=None) -> None:
        self.registry, self.dispatcher, self.engine, self.store, self.services = registry, dispatcher, engine, store, services

    async def handle(self, chat_id: str, text: str) -> str | None:
        """Returns the reply, or None when nothing matched (caller decides the fallback)."""
        word = text.strip().lower()
        command = word.lstrip("!/")
        ctx, chat = Context(chat_id, text, self.services), self.store.get(chat_id)

        # 0. menu and help always work, even mid-game (the game stays active)
        if command in MENU_WORDS or command == "help" or command.startswith("help "):
            return replies.home_menu(self.registry) if command in MENU_WORDS else replies.help_for(self.registry, command[4:])

        # 1. active game (stop/quit always ends it)
        if chat.session:
            if word in STOP_WORDS:
                self.store.set_session(chat_id, None)
                return "Game ended."
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
            return "pong 🏓"

        # 3. the bot asked a question: this message is the answer
        if chat.pending:
            p = chat.pending
            self.store.set_pending(chat_id, None)
            return await self._run(chat_id, p.feature, {**p.args, p.missing[0]: text.strip()}, ctx)

        # 4. intent engine
        key, last = " ".join(word.rstrip(".!?؟ ").split()), chat.repeat
        again = last if last and last.text == key else None          # the same message, sent again within a minute
        d: Decision = self.engine(text, self.registry.specs(), chat.last_turn)
        if d.kind in ("match", "followup"):
            spec = self.registry.spec(d.feature)
            if again and again.feature == d.feature and again.reply and spec and spec.repeat == "reuse":
                self.store.set_repeat(chat_id, Repeat(key, d.feature, again.reply, again.count + 1))
                return replies.repeated(again.reply, again.count + 1)
            return await self._run(chat_id, d.feature, d.args, ctx, key, again)
        if d.kind == "clarify":
            self.store.set_pending(chat_id, Pending(d.feature, d.args, d.missing))
            return d.question
        self.store.set_repeat(chat_id, Repeat(key, None, None, again.count + 1 if again else 1))
        return None

    async def respond(self, chat_id: str, text: str) -> str:
        """handle(), plus a fallback for messages nothing understood (which changes if it is repeated)."""
        if reply := await self.handle(chat_id, text):
            return reply
        last = self.store.get(chat_id).repeat
        return replies.not_understood(self.registry, last.count if last else 1, text)

    async def _run(self, chat_id: str, feature: str, args: dict, ctx: Context,
                   key: str = "", again: Repeat | None = None) -> str:
        run = await self.dispatcher.run_feature(feature, args, ctx)
        if run.ok and run.session:
            tool = feature.partition(".")[0]
            self.store.set_session(chat_id, ActiveSession(tool, run.session.state))
        elif run.ok:
            self.store.set_last_turn(chat_id, LastTurn(feature, run.args))
            if key:
                count = again.count + 1 if again and again.feature == feature else 1
                self.store.set_repeat(chat_id, Repeat(key, feature, run.reply, count))
        return run.reply
