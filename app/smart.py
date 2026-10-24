"""Routing: one fixed order. Reads Decision and results only - it imports no NLU code."""
from app import replies
from app.core.context import ActiveSession, ContextStore, Pending
from app.core.dispatcher import Dispatcher
from app.core.registry import Registry
from app.core.schemas import Context, Continue, Finish, PassThrough
from app.intent.decision import Decision, IntentEngine, LastTurn

GREETINGS = {"hi", "hello", "hey", "salam", "assalamualaikum"}
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

        # 3. greeting
        if word in GREETINGS:
            return replies.greeting(self.registry)

        # 4. the bot asked a question: this message is the answer
        if chat.pending:
            p = chat.pending
            self.store.set_pending(chat_id, None)
            return await self._run(chat_id, p.feature, {**p.args, p.missing[0]: text.strip()}, ctx)

        # 5. intent engine
        d: Decision = self.engine(text, self.registry.specs(), chat.last_turn)
        if d.kind in ("match", "followup"):
            return await self._run(chat_id, d.feature, d.args, ctx)
        if d.kind == "clarify":
            self.store.set_pending(chat_id, Pending(d.feature, d.args, d.missing))
            return d.question
        return None

    async def _run(self, chat_id: str, feature: str, args: dict, ctx: Context) -> str:
        run = await self.dispatcher.run_feature(feature, args, ctx)
        if run.ok and run.session:
            tool = feature.partition(".")[0]
            self.store.set_session(chat_id, ActiveSession(tool, run.session.state))
        elif run.ok:
            self.store.set_last_turn(chat_id, LastTurn(feature, run.args))
        return run.reply
