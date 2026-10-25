"""The WAHA sender: a small keep-alive client for http:// URLs, tested against a scripted server that misbehaves like real servers do."""
import asyncio
import json
import time

import pytest

from app import waha
from app.settings import Settings
from app.waha import FastClient, HttpxClient, WahaError


class Server:
    """A scripted HTTP/1.1 server. `script(n, request)` returns an instruction for the n-th request overall:
       bytes                 the raw response to write
       ("close", bytes)      write it, then close the connection
       ("drop",)             close the connection without answering
       ("hang",)             never answer"""

    def __init__(self, script=None):
        self.script = script or (lambda n, req: ok())
        self.requests: list[dict] = []
        self.connections = 0
        self._server = None
        self._writers: set = set()

    async def start(self):
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self):
        self._server.close()
        for w in list(self._writers):                  # a client that kept its pooled connection open must not stall the shutdown
            w.close()
        await asyncio.wait_for(self._server.wait_closed(), 5)

    async def _serve(self, reader, writer):
        self.connections += 1
        self._writers.add(writer)
        try:
            while True:
                try:
                    head = await reader.readuntil(b"\r\n\r\n")
                except (asyncio.IncompleteReadError, ConnectionError):
                    return
                lines = head.decode().split("\r\n")
                headers = {k.lower(): v.strip() for k, _, v in (l.partition(":") for l in lines[1:] if l)}
                body = await reader.readexactly(int(headers.get("content-length", 0)))
                req = {"line": lines[0], "headers": headers, "body": body}
                self.requests.append(req)
                action = self.script(len(self.requests), req)
                if isinstance(action, bytes):
                    writer.write(action)
                    await writer.drain()
                elif action[0] == "close":
                    writer.write(action[1])
                    await writer.drain()
                    return
                elif action[0] == "drop":
                    return
                elif action[0] == "hang":
                    await reader.read()                      # say nothing; ends when the client gives up and closes
                    return
        finally:
            self._writers.discard(writer)
            writer.close()


def ok(status="201 Created", body=b'{"id": "true_1@c.us"}', extra=""):
    return f"HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n{extra}\r\n".encode() + body


async def with_server(script=None):
    return await Server(script).start()


# --- the happy path -------------------------------------------------------------------------------------------------------------
async def test_posts_json_with_the_right_headers_and_reads_the_response():
    srv = await with_server()
    try:
        client = FastClient("127.0.0.1", srv.port, api_key="k3y")
        status, body = await client.post("/api/sendText", {"session": "default", "chatId": "1@c.us", "text": "héllo 🏓"})
        await client.close()
    finally:
        await srv.stop()
    req = srv.requests[0]
    assert status == 201 and json.loads(body) == {"id": "true_1@c.us"}
    assert req["line"] == "POST /api/sendText HTTP/1.1" and req["headers"]["x-api-key"] == "k3y"
    assert req["headers"]["content-type"] == "application/json" and req["headers"]["host"] == f"127.0.0.1:{srv.port}"
    assert json.loads(req["body"]) == {"session": "default", "chatId": "1@c.us", "text": "héllo 🏓"}      # UTF-8 intact, length header matched


async def test_no_api_key_header_when_none_is_configured():
    srv = await with_server()
    try:
        await FastClient("127.0.0.1", srv.port).post("/x", {})
    finally:
        await srv.stop()
    assert "x-api-key" not in srv.requests[0]["headers"]


async def test_connections_are_reused():
    srv = await with_server()
    try:
        client = FastClient("127.0.0.1", srv.port)
        for _ in range(25):
            await client.post("/x", {"i": 1})
        await client.close()
    finally:
        await srv.stop()
    assert len(srv.requests) == 25 and srv.connections == 1


async def test_many_concurrent_sends_use_a_bounded_pool():
    srv = await with_server(lambda n, req: ok())
    try:
        client = FastClient("127.0.0.1", srv.port, max_connections=8)
        results = await asyncio.gather(*(client.post("/x", {"i": i}) for i in range(80)))
        await client.close()
    finally:
        await srv.stop()
    assert all(s == 201 for s, _ in results) and len(srv.requests) == 80 and srv.connections <= 8


# --- response framing ----------------------------------------------------------------------------------------------------------
async def test_chunked_responses_are_decoded():
    chunked = b"HTTP/1.1 201 Created\r\nTransfer-Encoding: chunked\r\n\r\n5\r\n{\"id\"\r\n7;ext=1\r\n: \"abc\"\r\n2\r\n}\n\r\n0\r\nX-Trailer: 1\r\n\r\n"
    srv = await with_server(lambda n, req: chunked)
    try:
        client = FastClient("127.0.0.1", srv.port)
        s1, b1 = await client.post("/x", {})
        s2, b2 = await client.post("/x", {})                     # and the connection is still in sync afterwards
    finally:
        await srv.stop()
    assert (s1, b1) == (201, b'{"id": "abc"}\n') == (s2, b2) and srv.connections == 1


async def test_connection_close_is_honoured():
    srv = await with_server(lambda n, req: ok(extra="Connection: close\r\n"))
    try:
        client = FastClient("127.0.0.1", srv.port)
        for _ in range(3):
            assert (await client.post("/x", {}))[0] == 201
    finally:
        await srv.stop()
    assert srv.connections == 3


async def test_a_body_without_length_ends_at_eof_and_is_not_reused():
    srv = await with_server(lambda n, req: ("close", b"HTTP/1.0 200 OK\r\n\r\nhello"))
    try:
        client = FastClient("127.0.0.1", srv.port)
        assert await client.post("/x", {}) == (200, b"hello")
        assert await client.post("/x", {}) == (200, b"hello")
    finally:
        await srv.stop()
    assert srv.connections == 2


async def test_continue_and_no_content_responses():
    script = {1: b"HTTP/1.1 100 Continue\r\n\r\n" + ok(), 2: b"HTTP/1.1 204 No Content\r\n\r\n"}
    srv = await with_server(lambda n, req: script[n])
    try:
        client = FastClient("127.0.0.1", srv.port)
        assert (await client.post("/x", {}))[0] == 201
        assert await client.post("/x", {}) == (204, b"")
        assert srv.connections == 1
    finally:
        await srv.stop()


async def test_error_statuses_are_returned_not_raised_by_the_client():
    srv = await with_server(lambda n, req: ok("500 Internal Server Error", b'{"error": "boom"}'))
    try:
        assert await FastClient("127.0.0.1", srv.port).post("/x", {}) == (500, b'{"error": "boom"}')
    finally:
        await srv.stop()


# --- failure handling ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("garbage", [b"garbage\r\n\r\n", b"HTTP/1.1 abc\r\n\r\n", b"\x00\x01\x02\r\n\r\n"])
async def test_non_http_replies_raise_waha_error(garbage):
    srv = await with_server(lambda n, req: garbage)
    try:
        with pytest.raises(WahaError, match="not HTTP"):
            await FastClient("127.0.0.1", srv.port).post("/x", {})
    finally:
        await srv.stop()


async def test_truncated_responses_raise_and_are_not_retried():
    srv = await with_server(lambda n, req: ("close", b"HTTP/1.1 201 Created\r\nContent-Length: 50\r\n\r\nshort"))
    try:
        with pytest.raises(WahaError, match="truncated"):
            await FastClient("127.0.0.1", srv.port).post("/x", {})
    finally:
        await srv.stop()
    assert len(srv.requests) == 1                                  # the server had answered (partially): resending could duplicate the message


async def test_a_server_that_hangs_times_out():
    srv = await with_server(lambda n, req: ("hang",))
    try:
        start = time.perf_counter()
        with pytest.raises(WahaError, match="did not answer"):
            await FastClient("127.0.0.1", srv.port, timeout=0.3).post("/x", {})
        assert time.perf_counter() - start < 2
    finally:
        await srv.stop()


async def test_connection_refused():
    with pytest.raises(WahaError, match="unreachable"):
        await FastClient("127.0.0.1", 1, timeout=2).post("/x", {})


async def test_an_oversized_body_is_refused():
    srv = await with_server(lambda n, req: b"HTTP/1.1 200 OK\r\nContent-Length: 99999999\r\n\r\n")
    try:
        with pytest.raises(WahaError, match="oversized"):
            await FastClient("127.0.0.1", srv.port).post("/x", {})
    finally:
        await srv.stop()


async def test_a_stale_pooled_connection_is_retried_on_a_fresh_one():
    """Node closes idle keep-alive connections; the next request must still succeed (the closed one never processed it)."""
    def script(n, req):
        return ("close", ok()) if n == 1 else ok()                 # answer the first request, then close the connection
    srv = await with_server(script)
    try:
        client = FastClient("127.0.0.1", srv.port)
        assert (await client.post("/x", {"n": 1}))[0] == 201
        await asyncio.sleep(0.1)                                   # the server's close reaches us
        assert (await client.post("/x", {"n": 2}))[0] == 201
    finally:
        await srv.stop()
    assert srv.connections == 2 and len(srv.requests) == 2


async def test_a_connection_that_drops_after_the_request_is_retried_once_only():
    srv = await with_server(lambda n, req: ok() if n == 1 else ("drop",))
    try:
        client = FastClient("127.0.0.1", srv.port)
        await client.post("/x", {})
        with pytest.raises(WahaError, match="closed the connection"):
            await client.post("/x", {})
    finally:
        await srv.stop()
    assert len(srv.requests) == 3                                  # request 2 on the reused connection, its single retry (3); then give up


async def test_idle_connections_older_than_the_limit_are_not_reused(monkeypatch):
    srv = await with_server()
    try:
        client = FastClient("127.0.0.1", srv.port)
        monkeypatch.setattr(FastClient, "MAX_IDLE_AGE", 0.05)
        await client.post("/x", {})
        await asyncio.sleep(0.1)
        await client.post("/x", {})
    finally:
        await srv.stop()
    assert srv.connections == 2


# --- send_text and backend selection ---------------------------------------------------------------------------------------------
@pytest.fixture
def waha_env(monkeypatch):
    def configure(**env):
        for k, v in {"WAHA_URL": None, "WAHA_CLIENT": None, "WAHA_API_KEY": None, **env}.items():
            monkeypatch.delenv(k, raising=False) if v is None else monkeypatch.setenv(k, v)
        from app.settings import get_settings
        get_settings.cache_clear()
        waha._backend = waha._backend_loop = None
    yield configure
    from app.settings import get_settings
    get_settings.cache_clear()
    waha._backend = waha._backend_loop = None


@pytest.mark.parametrize("env, kind", [
    ({"WAHA_URL": "http://localhost:3000"}, FastClient), ({"WAHA_URL": "http://waha:3000", "WAHA_CLIENT": "fast"}, FastClient),
    ({"WAHA_URL": "https://waha.example.com"}, HttpxClient), ({"WAHA_URL": "http://localhost:3000", "WAHA_CLIENT": "httpx"}, HttpxClient),
    ({"WAHA_URL": "http://proxy.example.com/waha"}, HttpxClient)])
def test_backend_selection(waha_env, env, kind):
    waha_env(**env)
    assert isinstance(waha.make_client(), kind)


async def test_send_text_posts_the_documented_payload_and_raises_on_errors(waha_env):
    srv = await with_server(lambda n, req: ok() if n == 1 else ok("422 Unprocessable Entity", b'{"message": "no such session"}'))
    waha_env(WAHA_URL=f"http://127.0.0.1:{srv.port}", WAHA_API_KEY="abc")
    try:
        await waha.send_text("default", "923001234567@c.us", "hello")
        assert json.loads(srv.requests[0]["body"]) == {"session": "default", "chatId": "923001234567@c.us", "text": "hello"}
        assert srv.requests[0]["headers"]["x-api-key"] == "abc"
        with pytest.raises(WahaError, match="422"):
            await waha.send_text("nope", "1@c.us", "x")
    finally:
        await waha.close()
        await srv.stop()


async def test_the_httpx_backend_behaves_the_same(waha_env):
    srv = await with_server(lambda n, req: ok() if n == 1 else ok("500 Internal Server Error", b"{}"))
    waha_env(WAHA_URL=f"http://127.0.0.1:{srv.port}", WAHA_CLIENT="httpx")
    try:
        assert isinstance(waha._client(), HttpxClient)
        await waha.send_text("default", "1@c.us", "hello")
        with pytest.raises(WahaError, match="500"):
            await waha.send_text("default", "1@c.us", "again")
    finally:
        await waha.close()
        await srv.stop()
    with pytest.raises(WahaError, match="unreachable"):
        waha_env(WAHA_URL="http://127.0.0.1:1", WAHA_CLIENT="httpx")
        try:
            await waha.send_text("default", "1@c.us", "x")
        finally:
            await waha.close()


async def test_a_new_event_loop_gets_a_new_backend(waha_env):
    waha_env(WAHA_URL="http://127.0.0.1:9")
    first = waha._client()
    waha._backend_loop = object()                                  # pretend the backend was created in another (closed) loop
    assert waha._client() is not first


# --- why it exists -------------------------------------------------------------------------------------------------------------
async def test_the_fast_client_costs_a_fraction_of_httpx_cpu(waha_env):
    srv = await with_server()
    try:
        fast, slow = FastClient("127.0.0.1", srv.port), HttpxClient(f"http://127.0.0.1:{srv.port}")
        for c in (fast, slow):
            await c.post("/api/sendText", {"text": "warm"})
        timings = {}
        for name, c in (("fast", fast), ("httpx", slow)):
            start = time.process_time()
            for i in range(300):
                await c.post("/api/sendText", {"session": "default", "chatId": f"{i}@c.us", "text": "hello"})
            timings[name] = time.process_time() - start
        await fast.close()
        await slow.close()
    finally:
        await srv.stop()
    assert timings["fast"] * 3 < timings["httpx"], timings          # measured ~10x on an idle machine; 3x leaves room for a noisy one
