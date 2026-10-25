"""WAHA client: sends replies.

Two interchangeable backends behind `send_text`:
  fast   a small keep-alive HTTP/1.1 client over asyncio streams, for plain `http://host:port` WAHA URLs (WAHA normally runs next to the bot).
         Measured: ~0.1 ms of CPU per reply against ~1.9 ms for httpx, a third of the bot's whole cost per message.
  httpx  the general client; used automatically for https:// or a URL with a path, or when WAHA_CLIENT=httpx (the escape hatch).
Both raise WahaError on any failure, so callers handle one exception type."""
import asyncio
import json
import time

import httpx

from app.settings import get_settings


class WahaError(RuntimeError):
    """WAHA could not be reached, timed out, answered with an error status, or sent something that is not HTTP."""


class _Stale(Exception):
    """A reused keep-alive connection turned out to be closed by the server before it sent a single byte back (nothing was processed)."""


class FastClient:
    MAX_IDLE_AGE = 4.0          # seconds. Node (WAHA) closes idle keep-alive connections after 5 s, so never reuse one that has rested longer
    MAX_IDLE = 64
    MAX_BODY = 1_000_000

    def __init__(self, host: str, port: int, api_key: str = "", timeout: float = 15, max_connections: int = 64) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self._head = (f"Host: {host}{'' if port == 80 else f':{port}'}\r\nContent-Type: application/json\r\nAccept: application/json\r\n"
                      + (f"X-Api-Key: {api_key}\r\n" if api_key else ""))
        self._idle: list[tuple[asyncio.StreamReader, asyncio.StreamWriter, float]] = []
        self._slots = asyncio.Semaphore(max_connections)

    async def post(self, path: str, payload: dict) -> tuple[int, bytes]:
        body = json.dumps(payload, ensure_ascii=False).encode()
        request = f"POST {path} HTTP/1.1\r\n{self._head}Content-Length: {len(body)}\r\n\r\n".encode() + body
        async with self._slots:
            try:
                return await asyncio.wait_for(self._exchange(request), self.timeout)
            except asyncio.TimeoutError:
                raise WahaError(f"WAHA did not answer within {self.timeout:g}s") from None

    async def _exchange(self, request: bytes) -> tuple[int, bytes]:
        for attempt in (0, 1):
            (reader, writer), reused = await self._acquire()
            try:
                writer.write(request)
                await writer.drain()
                status, data, keep = await self._read_response(reader)
            except (_Stale, ConnectionError, BrokenPipeError):
                self._discard(writer)
                if reused and attempt == 0:
                    continue                    # the pooled connection was dead: retry once on a fresh one (the request was never processed)
                raise WahaError("WAHA closed the connection") from None
            except asyncio.CancelledError:
                self._discard(writer)
                raise
            except Exception:
                self._discard(writer)
                raise
            self._release(reader, writer) if keep else self._discard(writer)
            return status, data
        raise WahaError("unreachable")          # pragma: no cover

    async def _acquire(self):
        while self._idle:
            reader, writer, since = self._idle.pop()
            if writer.is_closing() or reader.at_eof() or time.monotonic() - since > self.MAX_IDLE_AGE:
                self._discard(writer)
                continue
            return (reader, writer), True
        try:
            return await asyncio.open_connection(self.host, self.port, limit=2 ** 16), False
        except OSError as e:
            raise WahaError(f"WAHA unreachable at {self.host}:{self.port}: {e}") from None

    def _release(self, reader, writer) -> None:
        if len(self._idle) >= self.MAX_IDLE:
            self._discard(writer)
        else:
            self._idle.append((reader, writer, time.monotonic()))

    @staticmethod
    def _discard(writer) -> None:
        try:
            writer.close()
        except Exception:                        # noqa: BLE001 - closing a dead socket may itself fail; nothing to do about it
            pass

    async def _read_head(self, reader) -> tuple[int, str, dict[str, str]]:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except asyncio.IncompleteReadError as e:
            if not e.partial:
                raise _Stale() from None         # EOF before any byte: the server had already closed this connection
            raise WahaError("WAHA sent a truncated response") from None
        except asyncio.LimitOverrunError:
            raise WahaError("WAHA sent an oversized response header") from None
        lines = head.decode("latin-1").split("\r\n")
        parts = lines[0].split(" ", 2)
        if len(parts) < 2 or not parts[0].startswith("HTTP/") or not parts[1].isdigit():
            raise WahaError(f"WAHA sent something that is not HTTP: {lines[0][:60]!r}")
        headers = {k.strip().lower(): v.strip() for k, _, v in (l.partition(":") for l in lines[1:] if l)}
        return int(parts[1]), parts[0], headers

    async def _read_response(self, reader) -> tuple[int, bytes, bool]:
        status, version, headers = await self._read_head(reader)
        while 100 <= status < 200 and status != 101:                  # "100 Continue" etc.: the real response follows
            status, version, headers = await self._read_head(reader)
        keep = version == "HTTP/1.1" and "close" not in headers.get("connection", "").lower()
        try:
            if status in (204, 304) or 100 <= status < 200:
                return status, b"", keep
            if "chunked" in headers.get("transfer-encoding", "").lower():
                return status, await self._read_chunked(reader), keep
            if "content-length" in headers:
                n = int(headers["content-length"])
                if n > self.MAX_BODY:
                    raise WahaError("WAHA sent an oversized response body")
                return status, await reader.readexactly(n) if n else b"", keep
            return status, await reader.read(self.MAX_BODY), False        # no length: the body ends when the server closes
        except (asyncio.IncompleteReadError, ValueError):
            raise WahaError("WAHA sent a truncated or malformed response body") from None

    async def _read_chunked(self, reader) -> bytes:
        out = bytearray()
        while True:
            size = int((await reader.readuntil(b"\r\n")).split(b";")[0].strip() or b"0", 16)
            if size == 0:
                while (await reader.readuntil(b"\r\n")) != b"\r\n":      # trailers, until the blank line
                    pass
                return bytes(out)
            if len(out) + size > self.MAX_BODY:
                raise WahaError("WAHA sent an oversized response body")
            out += (await reader.readexactly(size + 2))[:-2]

    async def close(self) -> None:
        while self._idle:
            self._discard(self._idle.pop()[1])


class HttpxClient:
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 15) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, headers={"X-Api-Key": api_key} if api_key else {},
                                         limits=httpx.Limits(max_connections=100, max_keepalive_connections=50))

    async def post(self, path: str, payload: dict) -> tuple[int, bytes]:
        try:
            r = await self._client.post(path, json=payload)
        except httpx.TimeoutException:
            raise WahaError("WAHA did not answer in time") from None
        except httpx.HTTPError as e:
            raise WahaError(f"WAHA unreachable: {type(e).__name__}") from None
        return r.status_code, r.content

    async def close(self) -> None:
        await self._client.aclose()


_backend = None
_backend_loop = None


def make_client():
    """The backend for the configured WAHA_URL (see the module docstring for the rule)."""
    from urllib.parse import urlsplit
    s = get_settings()
    u = urlsplit(s.waha_url)
    if s.waha_client == "fast" and u.scheme == "http" and u.hostname and not u.path.strip("/") and not u.query:
        return FastClient(u.hostname, u.port or 80, s.waha_api_key)
    return HttpxClient(s.waha_url, s.waha_api_key)


def _client():
    """One backend per running event loop (connections belong to the loop that opened them)."""
    global _backend, _backend_loop
    loop = asyncio.get_running_loop()
    if _backend is None or _backend_loop is not loop:
        _backend, _backend_loop = make_client(), loop
    return _backend


async def send_text(session: str, chat_id: str, text: str) -> None:
    status, body = await _client().post("/api/sendText", {"session": session, "chatId": chat_id, "text": text})
    if status >= 400:
        raise WahaError(f"WAHA answered {status}: {body[:200]!r}")


async def close() -> None:
    """Called at shutdown so pooled connections are closed cleanly."""
    global _backend, _backend_loop
    if _backend is not None:
        await _backend.close()
        _backend = _backend_loop = None
