"""Simple WhatsApp bot: WAHA posts incoming messages to /webhook, we reply with a text."""
import logging

from fastapi import FastAPI, Request

from app.core.context import ContextStore
from app.core.dispatcher import Dispatcher
from app.core.registry import Registry
from app.core.services import Services
from app import replies
from app.intent.rule_based import decide
from app.smart import Bot
from app.waha import send_text

log = logging.getLogger("wa-bot")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Rory")


services = Services()
registry = Registry().discover()
bot = Bot(registry, Dispatcher(registry), decide, ContextStore(), services)


async def reply_for(chat_id: str, text: str) -> str:
    return await bot.handle(chat_id, text) or replies.not_understood(registry)


@app.post("/webhook")
async def webhook(request: Request):
    event = await request.json()
    if event.get("event") != "message":
        return {"ok": True}
    p = event.get("payload", {})
    chat_id, text = p.get("from", ""), p.get("body") or ""
    if p.get("fromMe") or not chat_id or not text:                  # ignore our own messages and empty events
        return {"ok": True}
    log.info("%s: %s", chat_id, text)
    await send_text(event.get("session", "default"), chat_id, await reply_for(chat_id, text))
    return {"ok": True}


@app.get("/health")
async def health():
    return {"ok": True}
