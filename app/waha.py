"""Minimal WAHA client: send a text message."""
import httpx

from app.settings import get_settings


async def send_text(session: str, chat_id: str, text: str) -> None:
    s = get_settings()
    headers = {"X-Api-Key": s.waha_api_key} if s.waha_api_key else {}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{s.waha_url}/api/sendText", headers=headers,
                              json={"session": session, "chatId": chat_id, "text": text})
        r.raise_for_status()
