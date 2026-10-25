"""Rory's WhatsApp entry point: WAHA posts incoming messages to /webhook; we acknowledge at once and reply in the background.

Flow of one message:  parse -> (ignore own / empty / non-text) -> duplicate? -> group etiquette -> [background:]
per-chat ordering -> rate limit -> length check -> Bot.respond -> send -> one structured log line.
"""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import replies, trace
from app.core.context import ContextStore
from app.core.dispatcher import Dispatcher
from app.core.registry import Registry
from app.core.services import Services
from app import auth
from app.groups import address
from app.inbox import Recorder
from app.guards import KeyedLocks, RateLimiter, Seen
from app.intent.rule_based import decide
from app.logsetup import chat_ref, setup_logging
from app.settings import get_settings
from app.smart import Bot
from app.webchat import BASE as WEB_DIR, router as web_router
from app import waha
from app.waha import send_text

settings = get_settings()                          # fails fast with a readable message if the environment is wrong
setup_logging(settings.log_json, settings.log_level)
log = logging.getLogger("wa-bot")

queue: asyncio.Queue | None = None            # set while the app runs (see lifespan); None means "no workers": fall back to background tasks
_workers: list[asyncio.Task] = []


async def _worker() -> None:
    while True:
        job = await queue.get()
        try:
            await process(job)
        finally:
            queue.task_done()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start the worker pool. The webhook only parses and enqueues, so WAHA gets its answer immediately however busy the bot is."""
    global queue
    queue = asyncio.Queue(maxsize=settings.queue_size)
    if not auth.configured(settings.webhook_hmac_key, settings.webhook_token):
        log.warning("webhook is NOT authenticated: anyone who can reach it can make the bot reply. Set WEBHOOK_HMAC_KEY (and the same value as "
                    "WHATSAPP_HOOK_HMAC_KEY for WAHA) to verify WAHA's signature.")
    _workers[:] = [asyncio.create_task(_worker()) for _ in range(settings.workers)]
    try:
        yield
    finally:
        try:
            await asyncio.wait_for(queue.join(), timeout=10)             # let queued replies finish on a normal shutdown
        except asyncio.TimeoutError:
            log.warning("shutdown: %d messages were still queued", queue.qsize())
        for w in _workers:
            w.cancel()
        queue = None
        await waha.close()


app = FastAPI(title="Rory", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
app.include_router(web_router)

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


def parse(event) -> tuple[Job | None, str]:
    """Cheap, I/O-free triage of a webhook event: (job, "") to process it, or (None, reason) to ignore it. Never raises, whatever the shape."""
    if not isinstance(event, dict) or event.get("event") != "message":
        return None, "not_a_message"
    p = event.get("payload")
    if not isinstance(p, dict):
        return None, "bad_payload"
    chat_id, body = p.get("from"), p.get("body")
    if not isinstance(chat_id, str) or not isinstance(body, str):
        return None, "bad_payload"
    text = body.strip()
    if p.get("fromMe") is True:
        return None, "own_message"
    if not chat_id or not text:
        return None, "empty"
    if chat_id.endswith("@broadcast"):
        return None, "broadcast"
    message_id = p.get("id") if isinstance(p.get("id"), str) else None
    if seen.duplicate(message_id):
        return None, "duplicate"
    me = event.get("me")
    me_id = me.get("id", "") if isinstance(me, dict) and isinstance(me.get("id", ""), str) else ""
    participant = p.get("participant") if isinstance(p.get("participant"), str) else None
    sender = participant or chat_id
    chat_ctx, my_ctx = bot.store.peek(chat_id), bot.store.peek(bot.person_key(chat_id, sender))       # peek: group chatter must not create state
    engaged = bool((chat_ctx and chat_ctx.session) or (my_ctx and my_ctx.pending))                    # a running game, or a question asked of THIS person
    addressed = address(text, p, me_id, settings.bot_name, settings.group_mode, engaged=engaged)
    if addressed is None and settings.group_mode == "mention" and chat_id.endswith("@g.us") and bot.expects_followup(chat_id, sender, text, settings.group_followup_window):
        addressed = text                                                # the same person following up on Rory's answer: no mention needed
    if addressed is None:
        return None, "group_not_addressed"
    session = event.get("session") if isinstance(event.get("session"), str) else "default"
    return Job(session, chat_id, participant or chat_id, addressed, message_id), ""


async def reply_for(chat_id: str, text: str, sender: str | None = None) -> str:
    return await bot.respond(chat_id, text, sender)


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
                reply = await (reply_for(job.chat_id, job.text) if job.sender == job.chat_id else reply_for(job.chat_id, job.text, job.sender))
            if reply:
                await send_text(job.session, job.chat_id, reply)
    except Exception:                                                   # noqa: BLE001 - one bad message must never take the worker down
        outcome = "failed"
        log.exception("message failed", extra={"chat": chat_ref(job.chat_id)})
    t = trace.current()
    log.info("handled", extra={"chat": chat_ref(job.chat_id), "outcome": outcome, "kind": t.get("kind"), "feature": t.get("feature"),
                               "ms": round((time.perf_counter() - started) * 1000), "in_chars": len(job.text),
                               "out_chars": len(reply) if reply else 0, "group": job.chat_id.endswith("@g.us")})


async def read_body(request: Request, limit: int) -> bytes | None:
    """The request body, or None if it is larger than `limit` (checked from the header first, then while streaming)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        return None
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


_auth_warned: dict[str, float] = {}


def _reject(reason: str) -> JSONResponse:
    """401 without saying which check failed; the reason goes to the log, at most one line per reason every 10 s (a flood must not flood the log)."""
    now = time.monotonic()
    if now - _auth_warned.get(reason, -99) > 10:
        _auth_warned[reason] = now
        log.warning("webhook rejected: %s", reason)
    return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)


@app.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks):
    body = await read_body(request, settings.max_body_bytes)
    if body is None:
        return JSONResponse({"ok": False, "error": "request too large"}, status_code=413)
    if auth.configured(settings.webhook_hmac_key, settings.webhook_token):
        if reason := auth.verify(body, request.headers, request.query_params, settings.webhook_hmac_key, settings.webhook_token):
            return _reject(reason)
    try:
        event = json.loads(body)
    except ValueError:
        return JSONResponse({"ok": False, "error": "body is not valid JSON"}, status_code=400)
    if not isinstance(event, dict):
        return JSONResponse({"ok": False, "error": "expected a JSON object"}, status_code=400)
    job, reason = parse(event)
    if job is None:
        log.debug("ignored", extra={"reason": reason})
        return {"ok": True}
    if queue is None:                                                   # no worker pool (a bare test client): run after the response
        background.add_task(process, job)
        return {"ok": True}
    try:
        queue.put_nowait(job)                                           # answer WAHA immediately: slow tools must not cause retries
    except asyncio.QueueFull:
        log.warning("queue full: asking WAHA to retry", extra={"queued": queue.qsize()})
        return JSONResponse({"ok": False, "error": "busy, retry"}, status_code=503)
    return {"ok": True}


@app.get("/health")
async def health():
    return {"ok": True}
