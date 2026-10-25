#!/usr/bin/env python3
"""Stress / load test for Rory. Safe by construction: it starts its OWN bot on a private port and points it at a fake WAHA that only
records replies, so nothing is ever sent to WhatsApp and your running server is never touched.

    scripts/stress_test.py all --quick            # ~20 s: every mode, small sizes (also run by the normal test suite)
    scripts/stress_test.py engine                 # how decision time grows with the number of tools (the scale curve)
    scripts/stress_test.py burst --users 500 --messages 10 --concurrency 200
    scripts/stress_test.py soak --seconds 120 --rate 80          # steady traffic: latency drift and memory growth
    scripts/stress_test.py abuse                  # floods, duplicates, oversized/malformed requests, groups
    scripts/stress_test.py burst --waha-delay 0.3 # a slow WAHA: the webhook must still acknowledge instantly
    ... --json out.json                           # machine-readable results

Only pure tools are driven (calculator, ping, greetings, help, unknown text) so results measure Rory, not third-party APIs.
Exit code 0 = every gate passed, 1 = a gate failed."""
import argparse
import asyncio
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402

RESULTS: dict = {"gates": {}, "metrics": {}}


# --- reporting ---------------------------------------------------------------------------------------------------------------
def pct(values: list[float], p: float) -> float:
    return sorted(values)[min(int(len(values) * p), len(values) - 1)] if values else 0.0


def gate(name: str, ok: bool, detail: str = "") -> None:
    RESULTS["gates"][name] = bool(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  - {detail}" if detail else ""))


def heading(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def latency_line(label: str, ms: list[float]) -> str:
    return f"{label}: p50 {pct(ms, .5):.0f} ms  p95 {pct(ms, .95):.0f} ms  p99 {pct(ms, .99):.0f} ms  max {max(ms, default=0):.0f} ms"


# --- the harness: fake WAHA + a real bot process -----------------------------------------------------------------------------
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeWaha:
    """A WAHA stand-in in its OWN process (so it cannot share a GIL with the load generator and distort the numbers). It appends every
    sendText call to a file as a JSON line; this class reads that file incrementally. Optionally slow, like a loaded WAHA."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay, self.port = delay, free_port()
        fd, self.path = tempfile.mkstemp(prefix="rory-waha-", suffix=".jsonl")
        os.close(fd)
        self._offset, self._records, self.proc = 0, [], None

    def start(self) -> None:
        self.proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_waha", "--port", str(self.port), "--delay", str(self.delay), "--out", self.path],
                                     cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.5).close()
                return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("fake WAHA did not start")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=5)

    @property
    def records(self) -> list[tuple[float, str, str]]:
        with open(self.path, "rb") as f:
            f.seek(self._offset)
            data = f.read()
        end = data.rfind(b"\n")
        if end >= 0:
            for line in data[: end + 1].splitlines():
                r = json.loads(line)
                self._records.append((r["t"], r["chat"], r["text"]))
            self._offset += end + 1
        return self._records

    def by_chat(self) -> dict[str, list[tuple[float, str]]]:
        out: dict[str, list] = {}
        for t, chat, text in list(self.records):
            out.setdefault(chat, []).append((t, text))
        return out


def serve_waha(port: int, delay: float, out: str) -> None:
    """The fake WAHA process (hidden mode `_waha`)."""
    app = FastAPI()
    sink = open(out, "ab", buffering=0)

    @app.post("/api/sendText")
    async def send(request: Request):
        body = await request.json()
        if delay:
            await asyncio.sleep(delay)
        sink.write((json.dumps({"t": time.time(), "chat": body["chatId"], "text": body["text"]}, ensure_ascii=False) + "\n").encode())
        return {"ok": True}

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error", access_log=False)


class Bot:
    """Rory in a subprocess, configured through the environment exactly like production."""

    def __init__(self, waha: FakeWaha, **env: str) -> None:
        self.port = free_port()
        self.tmp = tempfile.mkdtemp(prefix="rory-stress-")
        self.env = {**os.environ, "WAHA_URL": f"http://127.0.0.1:{waha.port}", "WAHA_API_KEY": "stress", "UNMATCHED_PATH": f"{self.tmp}/unmatched.jsonl",
                    "LOG_LEVEL": "WARNING", "RATE_LIMIT_MAX": "100000", "DEDUP_TTL": "300", **{k.upper(): str(v) for k, v in env.items()}}
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(self.port), "--log-level", "error", "--no-access-log"],
                                     env=self.env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time.time() + 30
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("bot exited at startup: " + (self.proc.stderr.read().decode()[-800:] if self.proc.stderr else ""))
            try:
                if httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.2)
        raise RuntimeError("bot did not become healthy in 30 s")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def cpu_seconds(self) -> float:
        """CPU time the bot process has used so far (ps prints [dd-]hh:mm:ss or m:ss.xx)."""
        out = subprocess.run(["ps", "-o", "time=", "-p", str(self.proc.pid)], capture_output=True, text=True).stdout.strip()
        try:
            parts = [float(x) for x in out.replace("-", ":").split(":")]
        except ValueError:
            return 0.0
        total = 0.0
        for x in parts:
            total = total * 60 + x
        return total

    def rss_mb(self) -> float:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(self.proc.pid)], capture_output=True, text=True).stdout.strip()
        return int(out) / 1024 if out else 0.0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/webhook"


class Rig:
    def __init__(self, waha_delay: float = 0.0, **bot_env: str) -> None:
        self.waha, self.bot_env, self.bot = FakeWaha(waha_delay), bot_env, None

    def __enter__(self) -> "Rig":
        self.waha.start()
        self.bot = Bot(self.waha, **self.bot_env)
        try:
            self.bot.start()
        except Exception:
            self.__exit__()
            raise
        return self

    def __exit__(self, *exc) -> None:
        if self.bot:
            self.bot.stop()
        self.waha.stop()


async def settle(rig: Rig, start: int, expected: int | None = None, quiet: float = 0.6, timeout: float = 60) -> list[tuple[float, str, str]]:
    """Wait until the replies after record `start` stop arriving (or `expected` have arrived), then return them."""
    deadline, last_n, last_change = time.time() + timeout, -1, time.time()
    while time.time() < deadline:
        n = len(rig.waha.records) - start
        if expected is not None and n >= expected:
            break
        if n != last_n:
            last_n, last_change = n, time.time()
        elif time.time() - last_change > quiet and expected is None:
            break
        await asyncio.sleep(0.05)
    return rig.waha.records[start:]


def event(chat: str, body: str, mid: str | None, group: bool = False) -> dict:
    p = {"from": chat, "body": body}
    if mid:
        p["id"] = mid
    return {"event": "message", "session": "default", "me": {"id": "1@c.us"}, "payload": p}


# --- a deliberately tiny HTTP client: httpx costs ~10 ms of CPU per request at high concurrency and would measure itself, not Rory ---------
class Conn:
    """One persistent HTTP/1.1 connection, like WAHA's. post() returns (status, body bytes); reconnects if the server closed it."""

    def __init__(self, port: int) -> None:
        self.port, self.r, self.w = port, None, None

    async def _open(self) -> None:
        self.r, self.w = await asyncio.open_connection("127.0.0.1", self.port)

    async def post(self, path: str, body: bytes, ctype: str = "application/json") -> tuple[int, bytes]:
        for attempt in (0, 1):
            try:
                if self.w is None or self.w.is_closing():
                    await self._open()
                self.w.write(f"POST {path} HTTP/1.1\r\nHost: rory\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
                await self.w.drain()
                head = await self.r.readuntil(b"\r\n\r\n")
                lines = head.split(b"\r\n")
                status = int(lines[0].split()[1])
                length = next((int(l.split(b":")[1]) for l in lines if l.lower().startswith(b"content-length")), 0)
                data = await self.r.readexactly(length) if length else b""
                if any(l.lower() == b"connection: close" for l in lines):
                    self.w.close()
                    self.w = None
                return status, data
            except (ConnectionError, asyncio.IncompleteReadError, OSError):
                self.w = None
                if attempt:
                    return -1, b""
        return -1, b""

    async def close(self) -> None:
        if self.w is not None and not self.w.is_closing():
            self.w.close()


def jbody(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode()


# --- the message mix: pure tools only, each with a check on its reply ---------------------------------------------------------
def make_message(user: int, j: int) -> tuple[str, "callable"]:
    """(text, check(reply) -> bool). Rotates calc / ping / greeting / unknown / help so the whole router is exercised."""
    kind = j % 5
    if kind == 0 or kind == 4:
        a, b = user, j
        return f"{a}+{b}", lambda r, a=a, b=b: f"{a}+{b} = *{a + b}*" in r
    if kind == 1:
        return "ping", lambda r: r == "pong 🏓"
    if kind == 2:
        return "hello", lambda r: bool(r.strip())
    if kind == 3:
        return f"zxqv wibble {user}", lambda r: "know" in r or "didn't get" in r
    return "help", lambda r: "Home" in r


# --- 1. engine scale curve ---------------------------------------------------------------------------------------------------
def run_engine(args) -> None:
    heading("ENGINE - decision time as the number of tools grows")
    from app.intent.rule_based import decide
    from tests.helpers import real_registry
    base = real_registry().specs()

    def clone(k: int):
        out = list(base)
        for i in range(1, k):
            out += [s.model_copy(update={"tool": f"{s.tool}{i}", "phrases": tuple(p if "{" in p else f"{p} x{i}" for p in s.phrases)}) for s in base]
        return out

    msgs = ["weather in lahore", "100 usd to pkr", "who is albert einstein", "wether in lahor", "blah blah blah blah", "weather next monday in karachi",
            "tell me a jest", "what's fifteen plus four", "please flip a coin", "the quick brown fox jumps over the lazy dog"]
    scales = [1, 5] if args.quick else args.scales
    print(f"  (CPU time per decision)\n  {'tools x':>8}{'features':>10}{'phrases':>9}{'mean ms':>10}{'p95 ms':>9}{'max ms':>9}")
    curve = {}
    for k in scales:
        specs = clone(k)
        decide("warm up", specs)
        t = []
        for _ in range(2 if k > 20 else 5):
            for m in msgs:
                s = time.process_time()                           # CPU time, not wall time: a busy machine must not blame the engine
                decide(m, specs)
                t.append((time.process_time() - s) * 1000)
        curve[k] = (statistics.mean(t), pct(t, .95))
        print(f"  {k:>8}{len(specs):>10}{sum(len(s.phrases) for s in specs):>9}{curve[k][0]:>10.1f}{curve[k][1]:>9.1f}{max(t):>9.1f}")
    RESULTS["metrics"]["engine_curve_ms_p95"] = {str(k): round(v[1], 2) for k, v in curve.items()}
    gate("1x: p95 < 25 ms", curve[1][1] < 25, f"{curve[1][1]:.1f} ms")
    if 5 in curve:
        gate("5x tools: p95 < 60 ms (linear growth, no cliff)", curve[5][1] < 60, f"{curve[5][1]:.1f} ms")
    if 20 in curve:
        ratio = curve[20][1] / max(curve[5][1], 0.01)
        print(f"  20x vs 5x: {ratio:.0f}x slower for 4x the phrases" + ("  <- cache cliff (see docs/ROADMAP.md: phrase index)" if ratio > 12 else ""))


# --- 2. burst ----------------------------------------------------------------------------------------------------------------
async def drive_users(rig: Rig, users: int, messages: int, concurrency: int, tag: str = "u") -> dict:
    """Every user sends `messages` messages in order over ONE connection (waiting only for the webhook acknowledgement, like WAHA does);
    up to `concurrency` users are active at once."""
    sent_at: dict[tuple[str, int], float] = {}
    checks: dict[tuple[str, int], "callable"] = {}
    acks, errors = [], 0
    sem = asyncio.Semaphore(concurrency)

    async def user(i: int):
        nonlocal errors
        chat = f"{tag}{i:06d}@c.us"
        conn = Conn(rig.bot.port)
        async with sem:
            for j in range(messages):
                text, check = make_message(i, j)
                checks[(chat, j)] = check
                sent_at[(chat, j)] = t0 = time.time()
                status, body = await conn.post("/webhook", jbody(event(chat, text, f"{chat}-{j}")))
                if status != 200:
                    errors += 1
                acks.append((time.time() - t0) * 1000)
        await conn.close()

    start = time.time()
    await asyncio.gather(*(user(i) for i in range(users)))
    return {"sent_at": sent_at, "checks": checks, "acks": acks, "errors": errors, "send_seconds": time.time() - start, "total": users * messages}


async def wait_for_replies(rig: Rig, expected: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(rig.waha.records) >= expected:
            return True
        await asyncio.sleep(0.1)
    return len(rig.waha.records) >= expected


def verify(rig: Rig, run: dict) -> dict:
    """Each chat must get exactly one correct reply per message, in the order the messages were sent."""
    by_chat, missing, wrong, latencies = rig.waha.by_chat(), 0, 0, []
    chats = {c for c, _ in run["sent_at"]}
    for chat in chats:
        replies = by_chat.get(chat, [])
        n = sum(1 for c, _ in run["sent_at"] if c == chat)
        missing += max(n - len(replies), 0)
        for j in range(min(n, len(replies))):
            t, text = replies[j]
            if not run["checks"][(chat, j)](text):
                wrong += 1                                                  # right count, wrong content or wrong order
            latencies.append((t - run["sent_at"][(chat, j)]) * 1000)
    extra = sum(max(len(by_chat.get(c, [])) - sum(1 for k, _ in run["sent_at"] if k == c), 0) for c in chats)
    return {"missing": missing, "wrong": wrong, "extra": extra, "latencies": latencies}


def run_burst(args) -> None:
    users, messages, conc = (60, 5, 60) if args.quick else (args.users, args.messages, args.concurrency)
    heading(f"BURST - {users} users x {messages} messages = {users * messages} messages, concurrency {conc}, WAHA delay {args.waha_delay}s")
    with Rig(args.waha_delay) as rig:
        rss0, cpu0 = rig.bot.rss_mb(), rig.bot.cpu_seconds()
        run = asyncio.run(drive_users(rig, users, messages, conc))
        got_all = asyncio.run(wait_for_replies(rig, run["total"], 30 + run["total"] / 200))
        cpu = rig.bot.cpu_seconds() - cpu0
        first_sent = min(run["sent_at"].values())
        total_seconds = max((t for t, _c, _x in rig.waha.records), default=time.time()) - first_sent         # first message sent -> last reply delivered
        throughput = run["total"] / max(total_seconds, 0.001)
        v = verify(rig, run)
        rss1, alive = rig.bot.rss_mb(), rig.bot.alive
    acks = run["acks"]
    print(f"  sent {run['total']} in {run['send_seconds']:.2f}s  ->  {run['total'] / run['send_seconds']:.0f} msg/s accepted; all replies done in {total_seconds:.2f}s")
    print("  " + latency_line("webhook acknowledgement", acks))
    print("  " + latency_line("reply (send -> WAHA receives it)", v["latencies"]))
    print(f"  processing throughput: {throughput:.0f} messages/s sustained (capacity of ONE bot process; WhatsApp traffic is typically a few per second)")
    print(f"  bot CPU: {cpu:.2f} s for {run['total']} messages = {cpu / run['total'] * 1000:.1f} ms per message (the load generator and fake WAHA share this machine)")
    print(f"  memory: {rss0:.0f} MB -> {rss1:.0f} MB   replies: {len(rig.waha.records)}/{run['total']}   missing {v['missing']}  wrong/out-of-order {v['wrong']}  duplicated {v['extra']}")
    RESULTS["metrics"]["burst"] = {"msg_per_s": round(run["total"] / run["send_seconds"]), "ack_p95_ms": round(pct(acks, .95)), "reply_p95_ms": round(pct(v["latencies"], .95)),
                                   "rss_growth_mb": round(rss1 - rss0), "bot_cpu_ms_per_msg": round(cpu / run["total"] * 1000, 1),
                                   "throughput_msg_per_s": round(throughput)}
    ack_limit, reply_limit = (1500, 5000) if args.quick else (500, 3000)
    gate("bot stayed alive", alive)
    gate("no HTTP errors", run["errors"] == 0, f"{run['errors']} errors")
    gate("every message got exactly one reply", got_all and v["missing"] == 0 and v["extra"] == 0, f"missing {v['missing']}, duplicated {v['extra']}")
    gate("replies are correct and in order within each chat", v["wrong"] == 0, f"{v['wrong']} wrong")
    gate(f"acknowledgement p95 < {ack_limit} ms (WAHA never waits for tools)", pct(acks, .95) < ack_limit, f"{pct(acks, .95):.0f} ms")
    gate(f"reply p95 < {reply_limit} ms", pct(v["latencies"], .95) < reply_limit, f"{pct(v['latencies'], .95):.0f} ms")
    floor = 10 if args.quick else 40
    gate(f"sustained throughput >= {floor} messages/s", throughput >= floor, f"{throughput:.0f} msg/s")
    if args.waha_delay:
        gate("a slow WAHA does not slow the webhook", pct(acks, .95) < max(ack_limit, args.waha_delay * 1000), f"ack p95 {pct(acks, .95):.0f} ms vs WAHA delay {args.waha_delay * 1000:.0f} ms")
    if not args.quick:
        gate("memory growth < 150 MB", rss1 - rss0 < 150, f"+{rss1 - rss0:.0f} MB")


# --- 3. soak -----------------------------------------------------------------------------------------------------------------
async def soak(rig: Rig, seconds: float, rate: float, users: int) -> tuple[list, list, list, int, int]:
    acks: list[tuple[float, float]] = []                    # (elapsed, ack ms)
    rss: list[tuple[float, float]] = []
    errors = sent = 0
    start = time.time()
    pool: asyncio.Queue = asyncio.Queue()
    for _ in range(64):
        pool.put_nowait(Conn(rig.bot.port))

    async def one(i: int):
        nonlocal errors
        chat = f"soak{i % users:05d}@c.us"
        text, _ = make_message(i % users, i % 7)
        conn = await pool.get()
        t0 = time.time()
        status, _b = await conn.post("/webhook", jbody(event(chat, text, f"soak-{i}")))
        errors += status != 200
        acks.append((t0 - start, (time.time() - t0) * 1000))
        pool.put_nowait(conn)

    async def sampler():
        while time.time() - start < seconds:
            rss.append((time.time() - start, await asyncio.to_thread(rig.bot.rss_mb)))
            await asyncio.sleep(max(seconds / 12, 0.5))

    tasks, i = [asyncio.create_task(sampler())], 0
    while (elapsed := time.time() - start) < seconds:
        due = int(elapsed * rate)
        while sent < due:
            tasks.append(asyncio.create_task(one(i)))
            i, sent = i + 1, sent + 1
        await asyncio.sleep(0.005)
    await asyncio.gather(*tasks)
    while not pool.empty():
        await pool.get_nowait().close()
    return acks, rss, [], errors, sent


def run_soak(args) -> None:
    seconds, rate = (4, 25) if args.quick else (args.seconds, args.rate)
    heading(f"SOAK - {rate:g} messages/s for {seconds:g} s across {args.users_soak} chats")
    with Rig(args.waha_delay) as rig:
        acks, rss, _, errors, sent = asyncio.run(soak(rig, seconds, rate, args.users_soak))
        asyncio.run(wait_for_replies(rig, sent, 20))
        replies, alive = len(rig.waha.records), rig.bot.alive
    third = seconds / 3
    early = [ms for t, ms in acks if t < third]
    late = [ms for t, ms in acks if t > 2 * third]
    print(f"  sent {sent}, replies {replies}, errors {errors}")
    print("  " + latency_line("acknowledgement, first third", early))
    print("  " + latency_line("acknowledgement, last third ", late))
    if rss:
        print("  memory over time: " + " -> ".join(f"{m:.0f}" for _, m in rss) + " MB")
    RESULTS["metrics"]["soak"] = {"sent": sent, "replies": replies, "early_p95_ms": round(pct(early, .95)), "late_p95_ms": round(pct(late, .95))}
    gate("bot stayed alive", alive)
    gate("no errors", errors == 0, f"{errors}")
    gate("every message got a reply", replies >= sent, f"{replies}/{sent}")
    gate("latency does not drift (last third p95 <= 3x first third + 50 ms)", pct(late, .95) <= 3 * pct(early, .95) + 50, f"{pct(early, .95):.0f} -> {pct(late, .95):.0f} ms")
    if not args.quick and len(rss) >= 6:
        half = rss[len(rss) // 2][1]
        gate("memory flat in the second half (< 25 MB growth)", rss[-1][1] - half < 25, f"{half:.0f} -> {rss[-1][1]:.0f} MB")


# --- 4. abuse ----------------------------------------------------------------------------------------------------------------
async def abuse_checks(rig: Rig, limit: int) -> dict:
    out, port = {}, rig.bot.port

    async def post(body, ctype="application/json", raw=False):
        conn = Conn(port)
        try:
            return await conn.post("/webhook", body if raw else jbody(body), ctype)
        finally:
            await conn.close()

    n0 = len(rig.waha.records)                                          # (a) one sender floods
    await asyncio.gather(*(post(event("flood@c.us", f"{i}+1", f"f{i}")) for i in range(limit * 4)))
    texts = [t for _, ch, t in await settle(rig, n0) if ch == "flood@c.us"]
    out["flood"] = (len(texts), sum("fast" in t for t in texts))

    n0 = len(rig.waha.records)                                          # (b) the same message id 25 times (WAHA retries)
    await asyncio.gather(*(post(event("dup@c.us", "ping", "same-id")) for _ in range(25)))
    out["dup"] = sum(1 for _, ch, _t in await settle(rig, n0) if ch == "dup@c.us")

    n0 = len(rig.waha.records)                                          # (c) oversized message
    await post(event("big@c.us", "a" * 5000, "big1"))
    out["oversize"] = ([t for _, ch, t in await settle(rig, n0, expected=1)] or [""])[0]

    statuses = []                                                       # (d) malformed requests
    for body, raw in ((b"not json", True), (b"", True), (b"[]", True), (jbody({"event": "message"}), True), (jbody({"event": "message", "payload": None}), True),
                      (jbody({"event": "message", "payload": {"from": 5, "body": 7}}), True), (b"x" * 2_000_000, True)):
        statuses.append((await post(body, raw=raw))[0])
    out["malformed"] = statuses

    n0 = len(rig.waha.records)                                          # (e) group chatter must be silent, addressed messages answered
    group = "1203630@g.us"
    await asyncio.gather(*(post(event(group, f"lol {i}", f"g{i}")) for i in range(30)))
    await post(event(group, "rory ping", "g-addressed"))
    out["group"] = [t for _, ch, t in await settle(rig, n0) if ch == group]

    n0 = len(rig.waha.records)                                          # (f) thousands of distinct chats, one message each
    t0 = time.time()
    await asyncio.gather(*(post(event(f"many{i}@c.us", "ping", f"m{i}")) for i in range(1500)))
    out["many"] = len(await settle(rig, n0, expected=1500))
    out["many_s"] = time.time() - t0
    return out


def run_abuse(args) -> None:
    limit = 12
    heading(f"ABUSE - floods, duplicates, oversized and malformed requests, group chatter (rate limit {limit}/30 s)")
    with Rig(0.0, rate_limit_max=limit, rate_limit_window=30, max_message_chars=1000) as rig:
        rss0 = rig.bot.rss_mb()
        r = asyncio.run(abuse_checks(rig, limit))
        alive, rss1 = rig.bot.alive, rig.bot.rss_mb()
        healthy = httpx.get(f"http://127.0.0.1:{rig.bot.port}/health", timeout=5).status_code == 200 if alive else False
    answered, notices = r["flood"]
    print(f"  flood: {limit * 4} messages from one sender -> {answered} replies ({notices} notice)")
    print(f"  duplicates: 25 webhooks with one message id -> {r['dup']} reply")
    print(f"  oversize: {r['oversize'][:60]!r}")
    print(f"  malformed request statuses: {r['malformed']}")
    print(f"  group: 30 unaddressed + 1 addressed -> {r['group']}")
    print(f"  many chats: 1500 distinct senders -> {r['many']} replies in {r['many_s']:.1f}s; memory {rss0:.0f} -> {rss1:.0f} MB")
    gate("flood: exactly the limit answered, plus one polite notice, the rest silent", answered == limit + 1 and notices == 1, f"{answered} replies, {notices} notice(s)")
    gate("duplicates: a retried message is answered once", r["dup"] == 1, f"{r['dup']}")
    gate("oversized message gets a polite refusal", "too long" in r["oversize"], r["oversize"][:50])
    gate("malformed requests never crash the bot (no 5xx, no dropped connection)", all(0 < s < 500 for s in r["malformed"]), f"{r['malformed']}")
    gate("group chatter is ignored, an addressed message is answered", r["group"] == ["pong 🏓"], f"{r['group']}")
    gate("1500 distinct chats all answered", r["many"] == 1500, f"{r['many']}")
    gate("bot alive and healthy after abuse", alive and healthy)
    gate("memory growth < 100 MB", rss1 - rss0 < 100, f"+{rss1 - rss0:.0f} MB")


# --- main --------------------------------------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["all", "engine", "burst", "soak", "abuse", "_waha"], help=argparse.SUPPRESS if False else None)
    ap.add_argument("--port", type=int, help=argparse.SUPPRESS)
    ap.add_argument("--delay", type=float, default=0.0, help=argparse.SUPPRESS)
    ap.add_argument("--out", help=argparse.SUPPRESS)
    ap.add_argument("--quick", action="store_true", help="small sizes (~20 s for all): used by the test suite")
    ap.add_argument("--users", type=int, default=300, help="burst: simulated users")
    ap.add_argument("--messages", type=int, default=10, help="burst: messages per user")
    ap.add_argument("--concurrency", type=int, default=150, help="burst: simultaneous webhook requests")
    ap.add_argument("--seconds", type=float, default=60, help="soak: duration")
    ap.add_argument("--rate", type=float, default=60, help="soak: messages per second")
    ap.add_argument("--users-soak", type=int, default=500, help="soak: distinct chats")
    ap.add_argument("--scales", type=int, nargs="+", default=[1, 5, 20], help="engine: tool-count multipliers")
    ap.add_argument("--waha-delay", type=float, default=0.0, help="seconds the fake WAHA takes to accept each reply")
    ap.add_argument("--json", metavar="FILE", help="write results as JSON")
    args = ap.parse_args()
    if args.mode == "_waha":
        serve_waha(args.port, args.delay, args.out)
        return 0

    started = time.time()
    modes = ["engine", "burst", "abuse", "soak"] if args.mode == "all" else [args.mode]
    for m in modes:
        {"engine": run_engine, "burst": run_burst, "soak": run_soak, "abuse": run_abuse}[m](args)
    failed = [g for g, ok in RESULTS["gates"].items() if not ok]
    heading(f"{'ALL GATES PASSED' if not failed else 'GATES FAILED: ' + '; '.join(failed)}  ({len(RESULTS['gates']) - len(failed)}/{len(RESULTS['gates'])}, {time.time() - started:.0f} s)")
    if args.json:
        Path(args.json).write_text(json.dumps(RESULTS, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
