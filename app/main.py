"""Simple WhatsApp bot: WAHA posts incoming messages to /webhook, we reply with a text."""
import logging

from fastapi import FastAPI, Request

from app.waha import send_text

log = logging.getLogger("wa-bot")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="WhatsApp Bot")


def reply_for(text: str) -> str:
    """The whole 'brain' for now: swap this function for real logic later."""
    word = text.strip().lower()
    if word in ("hi", "hello", "hey"):
        return "👋 Hello! Send *ping* to test me."
    if word == "ping":
        return "pong 🏓"
    return f"You said: {text.strip()}"


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
    await send_text(event.get("session", "default"), chat_id, reply_for(text))
    return {"ok": True}


@app.get("/health")
async def health():
    return {"ok": True}
