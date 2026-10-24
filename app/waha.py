"""Minimal WAHA client: send a text message."""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

WAHA_URL = os.getenv("WAHA_URL", "http://localhost:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")


async def send_text(session: str, chat_id: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{WAHA_URL}/api/sendText", headers={"X-Api-Key": WAHA_API_KEY},
                              json={"session": session, "chatId": chat_id, "text": text})
        r.raise_for_status()
