# Rory test plan

Goal: find out **quickly and automatically** when Rory misunderstands a message, when a tool breaks (or an API it depends on changes),
and where answers could be smarter. Everything here is executable.

```bash
.venv/bin/python -m pytest -q                       # ~12 s, offline, 2200+ checks: run before every commit
.venv/bin/python -m pytest -m live -q               # hits the real APIs (~45 s): "is any tool broken right now?"
.venv/bin/python scripts/quality_report.py          # scores + improvement candidates; exit 1 if a gate fails
.venv/bin/python scripts/quality_report.py --tests --live --log server.log --json report.json   # everything
```

## 1. The layers

| # | Layer | File | Catches |
|---|---|---|---|
| 1 | Registry & dispatcher contract | `tests/test_core.py` | bad tools rejected, args validated, errors hidden, timeouts, network message |
| 2 | **Engine unit tests** | `tests/test_intent_engine.py` | politeness/typo/elongation handling, keyword rule, apostrophes, negatives, **phrase self-consistency (every declared phrase routes to its own feature)**, **ties**, **ReDoS / worst-case speed** |
| 3 | **Intent corpus** | `tests/test_intent_corpus.py` + `tests/corpus/intents.py` | misrouted messages, false positives, wrong arguments, missing-input questions, per-feature accuracy (>= 97%), the **gaps backlog** (strict xfail) |
| 4 | Per-tool metadata | `tests/test_tools_nlu.py` | every `example` routes to its feature, every `negative` never does, chatter matches nothing |
| 4a | **NLU layer** | `tests/test_nlu_layer.py` | dates lifted out of slots, spoken maths, synonyms widen understanding but never turn chatter or out-of-scope requests into tool calls, synonym validation in the registry |
| 4b | **Synonym helper** | `tests/test_suggest.py` | the WordNet suggestion filters (symmetry guard, ambiguity, known words), against a tiny fake WordNet; the real CLI only when installed |
| 4c | **Out of scope** | `tests/test_out_of_scope.py` | honest replies for missing capabilities, statements are not requests, demand is filed by capability |
| 5 | **Follow-ups (auto-derived)** | `tests/test_followups.py` | every declared follow-up phrase of every tool: stays on the feature, changes only what it declares, keeps the rest, silent without context |
| 6 | **Conversations** | `tests/test_scenarios.py` + `tests/scenarios/` | multi-turn flows: follow-ups, clarifications, repeats, greetings, help, unknown words, games, expiry, outages |
| 7 | **Failure matrix** | `tests/test_tool_failures.py` | every tool x {connection refused, timeout, hung upstream, HTTP 500, 404, wrong JSON shape, empty result}: friendly message, no leak, recovers on the next message |
| 8 | **Reply quality** | `tests/test_reply_quality.py` | every example answer is clean (no `None`, HTML, unfilled `{x}`, stray blank lines), short enough to read on a phone, opens with an emoji headline, humanised numbers; every help/menu page is clean |
| 9a | **Customer safety (Phase 0)** | `tests/test_phase0.py` | non-blocking webhook, duplicate/retried webhooks, rate limits, bounded chat memory, group etiquette, settings validation, per-chat ordering, structured logs with no phone numbers |
| 9 | **Robustness** | `tests/test_robustness.py` | odd/hostile messages (empty, NUL, 3 000 chars, emoji walls, injection strings), 300 seeded random messages, chats stay isolated |
| 10 | **Live smoke** (`-m live`) | `tests/test_live_tools.py` | real API changed/down/slow (> 8 s), answers not about what was asked, follow-ups and link/news flows against the real world |
| 11 | **Report** | `scripts/quality_report.py` | all of the above as numbers, plus the improvement list and the **log miner** (`--log`) |

Offline tests use `tests/api_fixtures.py` (realistic response for every endpoint) through `tests/helpers.FakeHttp`, which fails the
way the network does (`httpx.ConnectError`, `ReadTimeout`, real `httpx.Response` with status codes), so the same tool code runs unmodified.

## 2. Quality gates (what "good" means)

| Gate | Threshold | Where |
|---|---|---|
| Intent accuracy per feature | >= 97% (currently 100% on 149 messages) | corpus test + report |
| False positives on chatter | 0 of 40 | corpus test + report |
| Arguments extracted with case intact | 100% | corpus `ARGS` |
| Every declared phrase routes to its own feature | 100% (913 phrases) | engine test |
| Order-dependent ties between features | 0 | engine test |
| Decision time | p95 < 25 ms (currently ~2 ms), adversarial input < 0.5 s | engine test + report |
| Tool failure handling | 7 failure modes x every network tool: friendly, no leaks | failure matrix |
| Reply well-formedness | 0 lint problems in 75 example replies and every help page | quality test |
| Known-gap backlog | each gap is a strict xfail: fixing one turns the suite red until you promote it | corpus test |

## 3. The improvement loop

1. **Collect.** Every message Rory cannot handle is also saved to the **improvement inbox** (`data/unmatched.jsonl`, never committed,
   chat ids hashed, pruned after 30 days): `unmatched` = nothing understood it, `tool_error` = a tool failed for a message that was
   understood. Review it with `scripts/unmatched.py list` (grouped by frequency, with the nearest known feature), turn rows into
   corpus lines with `scripts/unmatched.py corpus`, and hide handled ones with `review`. `quality_report.py` includes the inbox
   automatically. Besides that, the bot logs `unmatched: '<text>'` for every message nothing understood, and `tool handler failed: <feature>` /
   `upstream problem in <feature>` for tool problems. Run `scripts/quality_report.py --log server.log`: it groups unmatched messages
   by frequency, suggests the nearest known example, and counts tool crashes vs upstream outages per feature.
2. **Label.** Add the message to `tests/corpus/intents.py`: into `PLAIN`/`NOISY`/`WRAPPED` if it *should* already work, into `GAPS`
   (with a reason) if it needs engine work, into `NEGATIVE` if it must be ignored. Add `ARGS` for argument extraction.
3. **Fix.** Add a phrase to the tool (`phrases=[...]`), a `negatives` entry, or an engine improvement. Run pytest.
4. **Promote.** When a gap starts passing, its strict xfail goes red: move the line into the corpus. The backlog never goes stale.
5. **Re-measure.** `quality_report.py` shows accuracy, thin margins (fragile winners) and any new collisions.

What the first pass of this plan found and fixed: politeness wrappers and typos defeated matching; sentences containing a keyword
("the weather was terrible") triggered tools; a pending "Which place?" swallowed a different request; "what about X" with no context
produced "tell me about what about X"; malformed IP-lookup data printed `None`; OpenTDB being slow blocked quiz start for 12 s;
the engine recompiled 800 regexes per message (160 ms -> 2 ms); tic-tac-toe's first line broke the emoji-headline convention.

## 4. Adding a tool: the checklist (the tests do most of it)

1. Write `tools/<name>/tool.py` with `examples` (>= 2), `negatives` for any `keywords`, `repeat="reuse"` for idempotent lookups.
2. Add a realistic response for each new endpoint to `tests/api_fixtures.py`.
3. Add 3+ lines to `tests/corpus/intents.py` (a plain one, a noisy one, an `ARGS` one, and a near-miss to `NEGATIVE`).
4. Run `pytest -q`. The suite automatically exercises: its phrases (self-consistency, ties), examples/negatives, its follow-ups,
   its failure modes, and its reply quality. Add a scenario to `tests/scenarios/conversations.py` for any multi-turn behaviour.
5. Run `pytest -m live -k <name>` once to confirm the real API still matches the fixture.

## 5. Writing a conversation test

```python
Scenario("weather: switch city keeps the feature", [
    T("weather in lahore", has="Lahore"),
    T("what about karachi", http="Karachi"),            # an upstream call this turn mentioned Karachi
    T("what about karachi", wait=TURN_TTL + 1, has="lost track"),   # context expires after 5 minutes
])
```
`T(say, has, lacks, eq, rx, any_of, http, no_http, session, wait, fail, pre)`; every reply is linted automatically.
`fail="connect"|"timeout"|"500"|"404"|"malformed"|"empty"|"slow"` simulates an outage from that turn on; `fail=None` heals it.

## 6. Known limits (honest list)

* **Rule-based means phrase-based.** Open questions ("who invented the telephone"), maths in words, recommendations and real-time
  prices are documented gaps in `GAPS`, not silently wrong. A question-to-search fallback is the highest-value next step.
* **Link previews** fetch pages with their own hardened client, so they are only covered by live tests.
* **Relevance** ("is the answer about what was asked?") can only be judged against real data, so it lives in the live tests.
* **Typo repair** is deliberately conservative (5+ letter words, >= 0.9 similarity) so real words are never rewritten into commands;
  bigger typos fall back to a "Did you mean ...?" suggestion.
* Web search needs `GOOGLE_API_KEY` + `GOOGLE_CSE_ID`; its live test is skipped without them.
