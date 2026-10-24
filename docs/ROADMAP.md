# Rory roadmap: future expansion

Where Rory is today: a rule-based, tool-pluggable chat companion. 28 tools / 49 features / ~900 phrases, 10 games, a WAHA (WhatsApp)
webhook, in-memory chat context, 2,200+ offline tests and a quality report. This plan says what to build next, in what order, and how
each step is proven done with the existing test machinery (`docs/TEST_PLAN.md`).

Guiding rules (unchanged): **no LLM required**, drop-a-folder tools, core never edited to add a tool, every feature measurable.

## Phase 0 - Make it safe for real customers (do first, ~1 week)

| # | Work | Why | Done when |
|---|---|---|---|
| 0.1 | **Acknowledge the webhook immediately, reply in the background** (`BackgroundTasks` / queue) | WAHA waits for our answer; a slow tool (up to 15 s) can trigger a retry and a duplicate reply | webhook returns < 100 ms regardless of tool speed; test with a slow fake tool |
| 0.2 | **De-duplicate inbound messages** by WAHA message id (short TTL set) | retries and double webhooks happen | same payload twice -> one reply |
| 0.3 | **Per-user rate limit** (e.g. 12 msgs / 30 s, polite "slow down" reply) | spam, loops between two bots, quota protection | scenario test: 13th message in 30 s gets the limit notice, tools not called |
| 0.4 | **Evict idle chats** from `ContextStore` (and cap size) | memory grows with every chat ever seen | store stays bounded in a 10k-chat fuzz test |
| 0.5 | **Never reply to ourselves / groups opt-in**: ignore `fromMe`, optionally require a mention or prefix in groups | groups would otherwise be flooded | group fixture: only addressed messages answered |
| 0.6 | Config & secrets via one `Settings` object (pydantic-settings), `.env` validated at startup | misconfiguration today fails at first use | startup fails fast with a clear message |
| 0.7 | Structured logs (JSON) with chat hash, feature, latency, outcome | needed for every later phase; feeds `quality_report.py --log` | one log line per message with feature + ms |

## Phase 1 - Durable state and scaling (~1-2 weeks)

* **State store interface** (`ContextStore` becomes a protocol): in-memory (default) and **Redis** implementation for session, last turn,
  pending question, repeat, and per-tool memory (greetings seen, news shown). Survives restarts; lets you run N workers.
  Acceptance: the whole scenario suite runs unchanged against both backends (parametrise the fixture).
* **Phrase index** in the rule engine: bucket features by their first literal word / keywords so a message is only matched against
  plausible candidates; raise the compiled-pattern cache. Benchmarked today: 1.4 ms at 49 features, 7 ms at 5x, a cliff at 20x
  (pattern-cache thrash). Target: < 5 ms p95 at 50x. Acceptance: add a `tests/test_scale.py` that clones the registry 50x and asserts it.
* **Shared HTTP layer**: one client with per-host timeouts, retries with backoff for idempotent GETs, a small TTL cache for lookups
  (weather 10 min, currency 1 h, wiki 24 h) and a circuit breaker per upstream (after N failures answer "temporarily unavailable"
  instantly instead of waiting). Acceptance: failure matrix gains "N consecutive failures -> instant reply".
* **Observability**: `/health` (liveness), `/ready` (WAHA reachable), Prometheus `/metrics` (messages, per-feature latency, errors,
  unmatched count). Dashboard = unmatched rate, p95 per tool, upstream error rate.

## Phase 2 - Platform independence (~2 weeks)

Rory's core already speaks `chat_id + text -> reply`. Make that explicit and add platforms without touching tools.

* `app/platforms/` with a small `Platform` protocol: `parse(payload) -> Inbound`, `send(chat, Reply)`.
  Adapters: **WAHA** (exists, extract from `main.py`), **Telegram** (Bot API webhook, `sendMessage` with MarkdownV2 conversion),
  later Discord / Slack / a plain **HTTP/CLI** adapter (great for demos and tests).
* **Reply model** instead of a bare string: `Reply(text, buttons=[], image=None, audio=None, link_preview=True)`. Tools opt in;
  each adapter renders what it supports and degrades to text. Unlocks: real link aliases on Telegram (`[Read](url)`), buttons for
  news "1-5", polls for the games menu (the old branch did this on WhatsApp), images for link previews, Quran audio files.
* Formatting layer per platform: `format.tidy()` becomes `platform.format()` (WhatsApp `*bold*` vs Telegram MarkdownV2 escaping).
* Acceptance: the same 70 scenarios pass through the Telegram and CLI adapters using recorded payload fixtures.

## Phase 3 - Understanding more (rolling, driven by the log)

Order is set by `quality_report.py --log`, but the known backlog (`GAPS`) already points at the work:

1. **Open-question fallback**: "who invented the telephone", "when was Pakistan founded", "how tall is Everest" -> try Wikipedia
   search with the whole question, then web search, instead of "I didn't get that". Biggest single gain.
2. **Slot filling that spans tools**: dates/days ("next Monday", "kal"), multiple targets ("usd to pkr and eur"), units in words
   ("square root of 144", "15 times 4"). A small `slots` module (dates, numbers-in-words, currency names) shared by tools.
3. **Languages**: Roman Urdu / Urdu script / Arabic phrase packs per tool (`phrases_ur=[...]`), language detected per message,
   replies in the user's language where the tool supports it. Start with weather, news, greetings, Quran (already the audience).
4. **Context beyond one turn**: remember the user's default city / currency / Quran translation (`!settings`-style: "my city is
   Lahore", "set language urdu") so "weather" needs no place. Stored per user in the Phase 1 state store.
5. **Pluggable intent engines** (the interface already exists: one function). Add `INTENT_ENGINE=rules|hybrid|llm`:
   `hybrid` = rules first, then a model only for messages the rules left unmatched (optional, off by default, keeps "no LLM needed").
   The model sees metadata only, returns a `Decision`, and is validated by the same registry. Acceptance: corpus accuracy must not
   drop, `NEGATIVE` false positives stay 0, and cost/latency are logged per call.
6. **Learning loop**: `scripts/quality_report.py --log` already groups unmatched messages; add `--suggest` to propose phrases
   (nearest feature + the captured text) as a ready-to-paste corpus/phrase diff for review.

## Phase 4 - More tools (each is a folder; ranked by user value)

| Tool | Notes |
|---|---|
| **Reminders** (ported branch had them) | needs durable store + scheduler + proactive send; first feature that requires the Phase 1 store and Phase 2 `send` |
| **Prayer times / Qibla / Islamic date** | high value for the audience; Aladhan API (no key); uses the saved city |
| **Cricket scores & sports** | fixes the `cricket scores` gap; free feeds or search-backed |
| **Crypto & stock prices** | fixes `bitcoin price`; CoinGecko / Stooq |
| **Translate** | LibreTranslate / MyMemory; "translate hello to urdu" |
| **Dictionary & synonyms** | Free Dictionary API; "meaning of X" currently goes to Wikipedia |
| **Recipes, movies/TV recommendations** | "recommend a book like Dune" gap; TMDB/OpenLibrary subjects |
| **Currency/units upgrades** | multi-quote ("and"), crypto, historical rates |
| **Notes / todo / shopping list** | per-user durable data; teaches the state-store API |
| **Polls & group games** | scoreboards, turn-taking (needs group opt-in from Phase 0.5) |
| **Points, streaks, leaderboard** (old branch) | optional gamification once users persist |
| **Admin tools** | broadcast, stats, enable/disable tools per group, block list |

Every new tool follows the checklist in `docs/TEST_PLAN.md` section 4 and ships with fixtures, corpus lines and a live check.

## Phase 5 - Product and ops

* **Deployment**: Dockerfile + compose (bot, WAHA, Redis), a one-command start, HTTPS/tunnel guide, `/l/<id>` own short links when a
  public `BASE_URL` exists (the long Google News links become one short alias line each).
* **CI**: GitHub Actions running `pytest -q` on every push, `quality_report.py` as a gate, nightly `pytest -m live` that opens an
  issue when a real API breaks.
* **Security**: input length cap in the router, SSRF review for link previews (already blocks private IPs), dependency pinning and
  audit, secrets only from env, optional allow-list of chats.
* **Docs**: keep `ADDING_A_TOOL.md` current, add `ADDING_A_PLATFORM.md`, a runbook (restart, rotate WAHA key, read the logs).
* **Admin dashboard** (optional): read-only page over the metrics and the unmatched list, one-click "add as example".

## Suggested order and sizing

| Milestone | Contents | Size |
|---|---|---|
| M1 "Customer-safe" | Phase 0 | ~1 wk |
| M2 "Durable" | Phase 1 (state store, HTTP cache/breaker, metrics) | 1-2 wk |
| M3 "Everywhere" | Phase 2 (Platform + Reply model, Telegram) | ~2 wk |
| M4 "Smarter" | open-question fallback, slots, saved preferences, Urdu packs | 2-3 wk, then continuous |
| M5 "More" | reminders, prayer times, sports, crypto, translate | 1 wk per 1-2 tools |
| M6 "Operate" | Docker, CI, live nightly, dashboard | ~1 wk |

## Risks and how the plan contains them

* **Rule explosion** (phrases multiply, collisions return): the engine tests (self-consistency, ties, thin margins) and the phrase index
  keep it honest; consider generating phrases from a small grammar per tool if a tool exceeds ~60 phrases.
* **Upstream fragility** (free APIs change or vanish): live nightly + failure matrix + fixtures per endpoint; each tool names a
  fallback source in its README when one exists.
* **Platform limits** (WhatsApp has no link aliases or buttons via WAHA text): the `Reply` model degrades gracefully; do not design
  tools around features one platform lacks.
* **Scope creep into an LLM product**: keep the model strictly optional, behind the engine interface, and measured against the same corpus.

## Definition of done for any roadmap item

1. Offline tests added and green (`pytest -q`), including corpus lines for any new phrasing.
2. `scripts/quality_report.py` still passes every gate and the improvement list does not grow.
3. Live check passes for any new upstream (`pytest -m live -k <tool>`).
4. Docs updated (`ADDING_A_TOOL.md`, README table, this roadmap ticked).
