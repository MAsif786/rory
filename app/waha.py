"""Minimal WAHA client: send a text message. One shared connection pool (a new client per reply costs a TCP handshake and several ms of CPU)."""
import httpx

from app.settings import get_settings

_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    s = get_settings()
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=s.waha_url, timeout=15, headers={"X-Api-Key": s.waha_api_key} if s.waha_api_key else {},
                                    limits=httpx.Limits(max_connections=100, max_keepalive_connections=50))
    return _client


async def send_text(session: str, chat_id: str, text: str) -> None:
    r = await _http().post("/api/sendText", json={"session": session, "chatId": chat_id, "text": text})
    r.raise_for_status()


async def close() -> None:
    """Called at shutdown so the pool is closed cleanly."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
