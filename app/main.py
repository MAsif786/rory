"""Rory's WhatsApp entry point: WAHA posts incoming messages to /webhook; we acknowledge at once and reply in the background.

Flow of one message:  parse -> (ignore own / empty / non-text) -> duplicate? -> group etiquette -> [background:]
per-chat ordering -> rate limit -> length check -> Bot.respond -> send -> one structured log line.
"""
import logging
import time
from dataclasses import dataclass

from fastapi import BackgroundTasks, FastAPI, Request

from app import replies, trace
from app.core.context import ContextStore
from app.core.dispatcher import Dispatcher
from app.core.registry import Registry
from app.core.services import Services
from app.groups import address
from app.inbox import Recorder
from app.guards import KeyedLocks, RateLimiter, Seen
from app.intent.rule_based import decide
from app.logsetup import chat_ref, setup_logging
from app.settings import get_settings
from app.smart import Bot
from app.waha import send_text

settings = get_settings()                          # fails fast with a readable message if the environment is wrong
setup_logging(settings.log_json, settings.log_level)
log = logging.getLogger("wa-bot")

app = FastAPI(title="Rory")

RATE_NOTICE = "⏳ You're sending messages quite fast. Please wait a few seconds and try again."
TOO_LONG = "✂️ That message is too long for me (max {n} characters). Could you shorten it?"


def build_state() -> None:
    """(Re)create every piece of in-memory state. Tests call this to start clean."""
    global services, registry, bot, recorder, limiter, seen, locks
    services = Services()
    registry = Registry().discover()
    recorder = Recorder(settings.unmatched_path or None)
    recorder.prune(settings.unmatched_retention_days)
    bot = Bot(registry, Dispatcher(registry), decide, ContextStore(idle_ttl=settings.chat_idle_ttl, max_chats=settings.max_chats), services, recorder)
    limiter = RateLimiter(settings.rate_limit_max, settings.rate_limit_window)
    seen = Seen(settings.dedup_ttl)
    locks = KeyedLocks()


def reset_guards() -> None:
    """Fresh rate limiter, duplicate memory, locks and chat state (tests; also what a restart gives you)."""
    global limiter, seen, locks
    bot.store._chats.clear()
    limiter = RateLimiter(settings.rate_limit_max, settings.rate_limit_window)
    seen = Seen(settings.dedup_ttl)
    locks = KeyedLocks()


build_state()


@dataclass
class Job:
    session: str
    chat_id: str          # where to reply
    sender: str           # who is talking (the participant in a group): rate limits apply per sender
    text: str
    message_id: str | None


def parse(event: dict) -> tuple[Job | None, str]:
    """Cheap, I/O-free triage of a webhook event: (job, "") to process it, or (None, reason) to ignore it."""
    if event.get("event") != "message":
        return None, "not_a_message"
    p = event.get("payload") or {}
    chat_id, text = p.get("from") or "", (p.get("body") or "").strip()
    if p.get("fromMe"):
        return None, "own_message"
    if not chat_id or not text:
        return None, "empty"
    if chat_id.endswith("@broadcast") or chat_id == "status@broadcast":
        return None, "broadcast"
    if seen.duplicate(p.get("id")):
        return None, "duplicate"
    me_id = (event.get("me") or {}).get("id", "")
    ctx = bot.store.get(chat_id)
    addressed = address(text, p, me_id, settings.bot_name, settings.group_mode, engaged=bool(ctx.session or ctx.pending))
    if addressed is None:
        return None, "group_not_addressed"
    return Job(event.get("session", "default"), chat_id, p.get("participant") or chat_id, addressed, p.get("id")), ""


async def reply_for(chat_id: str, text: str) -> str:
    return await bot.respond(chat_id, text)


async def process(job: Job) -> None:
    started = time.perf_counter()
    trace.start()
    outcome, reply = "replied", None
    try:
        async with locks(job.chat_id):                                  # one message at a time per chat, in arrival order
            verdict = limiter.check(job.sender)
            if verdict == "drop":
                outcome = "rate_limited_silent"
            elif verdict == "notify":
                outcome, reply = "rate_limited", RATE_NOTICE
            elif len(job.text) > settings.max_message_chars:
                outcome, reply = "too_long", TOO_LONG.format(n=settings.max_message_chars)
            else:
                reply = await reply_for(job.chat_id, job.text)
            if reply:
                await send_text(job.session, job.chat_id, reply)
    except Exception:                                                   # noqa: BLE001 - one bad message must never take the worker down
        outcome = "failed"
        log.exception("message failed", extra={"chat": chat_ref(job.chat_id)})
    t = trace.current()
    log.info("handled", extra={"chat": chat_ref(job.chat_id), "outcome": outcome, "kind": t.get("kind"), "feature": t.get("feature"),
                               "ms": round((time.perf_counter() - started) * 1000), "in_chars": len(job.text),
                               "out_chars": len(reply) if reply else 0, "group": job.chat_id.endswith("@g.us")})


@app.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks):
    job, reason = parse(await request.json())
    if job:
        background.add_task(process, job)                               # answer WAHA immediately: slow tools must not cause retries
    else:
        log.debug("ignored", extra={"reason": reason})
    return {"ok": True}


@app.get("/health")
async def health():
    return {"ok": True}
