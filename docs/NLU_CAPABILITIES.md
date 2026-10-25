# Language understanding: what Rory has today, what it lacks, and the plan

Status as of 2026-10-25. Rory is rule-based (no LLM): every tool declares `phrases`, `keywords`, `negatives`, typed `inputs` and
`followups`; one small engine (`app/intent/rule_based.py`) matches messages against them. This page records, capability by capability,
what exists, the evidence, and what to build next. Roadmap context: `docs/ROADMAP.md` (Phase 3); measuring: `docs/TEST_PLAN.md`.

## 1. Status at a glance

| Capability | Status | Where / how it works today | Gap |
|---|---|---|---|
| Test corpus of real user messages | **Yes (small)** | `tests/corpus/intents.py`: ~150 labelled messages (`PLAIN`, `NOISY`, `WRAPPED`, `PROMOTED`, `REAL`), 40 chatter lines that must not match, argument checks (`ARGS`), clarification cases, and the `GAPS` backlog. The **improvement inbox** (`data/unmatched.jsonl`, `scripts/unmatched.py`) collects new real messages. | Few real messages yet (mostly the owner's own chats). Needs production traffic. |
| Spelling normalization | **Yes** | `variants()` tries, in order: politeness-stripped text, the original, de-elongated ("hii"->"hi"), typo-repaired ("wether"->"weather": words of 5+ letters, similarity >= 0.9). Apostrophes optional, case/punctuation ignored. Negatives are checked against the original text too. | Short-word typos ("oll", "wtr") only get a "Did you mean...?" suggestion. |
| Synonyms | **Partial** | No synonym layer: synonyms are enumerated as phrases per tool (913 phrases). Special tables exist inside tools: currency names->ISO codes, unit aliases, some Roman Urdu phrases. | No shared synonym/abbreviation table (`temp`, `info`, `rs`, `pls`, `u`). The old branch had one (`features.abbreviations`/`typos`); it was not ported. |
| Clarification questions | **Partial** | A missing *required input* asks a question (`Input.ask`), the next message fills it, a different request cancels it, an expired question is dropped. Unmatched near-misses: "Did you mean *X*?". | Nothing asks "A or B?" when two features score about the same: the engine silently takes the first. |
| Confidence thresholds | **No** | Matches are ranked internally `(kind, specificity)`; fixed cutoffs exist for typo repair (0.9), suggestions (0.6/0.7) and the keyword rule (<= 3 words). | No exposed confidence value and no per-tool threshold. Thin margins are only reported afterwards (`quality_report.py`). |
| Entity extraction: currencies | **Yes** | `currency` input patterns accept codes and names (`dollars`, `rupees`, `euros`...), amounts with separators. | Only the 20-ish currencies listed; crypto absent. |
| Entity extraction: numbers | **Partial** | Pattern-restricted slots: amounts, units, percentages, dice (`2d6`), verse references. | Numbers in words ("square root of 144", "fifteen times four"). |
| Entity extraction: cities | **Partial** | Captured from a phrase slot (`weather in {place}`) and validated by the geocoder (Open-Meteo). | No place gazetteer: a city is not recognised without a trigger phrase; slots accept almost any text. |
| Entity extraction: dates | **No** | Only literal phrases such as "tomorrow", "next week". | No date parser ("next monday", "the weekend", "kal", "in 3 days"). |
| Multi-intent detection | **No** | One message -> one intent (plus follow-ups to the previous answer). | No splitting of "weather in Lahore and time in Lahore". |

## 2. Evidence (probe run, offline engine)

| Message | Result today | Why it is wrong |
|---|---|---|
| `weather in lahore and time in lahore` | weather, place = `lahore and time in lahore` | two requests merged into one slot, then the geocoder fails |
| `weather in lahore and karachi` | weather, place = `lahore and karachi` | two places, one slot |
| `weather next monday in karachi` | weather, place = `next monday in karachi` | a date swallowed by the place slot |
| `forecast for the weekend in dubai` | forecast, place = `the weekend in dubai` | same |
| `list of jokes or facts` | country facts, country = `list of jokes or` | free-text slot accepts anything |
| `what is the temp in dubai` | Wikipedia lookup of `the temp in dubai` | abbreviation unknown, so a generic question phrase wins |
| `weather tomorrow` | nothing | a date without a place is not understood (should ask "Which place?") |
| `100 usd to pkr and eur` | nothing | only comma-separated quotes are supported |
| `temp in lahore` | nothing | no synonym for `temp` |

**Root cause (one thing, three symptoms):** the engine matches whole phrases whose placeholders are free text. Nothing extracts
*entities* (dates, numbers-in-words, multiple targets) *before* phrase matching, so whatever follows a trigger word is swallowed by the
slot. The fix is a pre-pass that lifts entities out of the text and leaves a clean phrase behind, not more phrases.

## 3. Plan (in order of value)

Each step ships with corpus lines, `GAPS` promotions, engine unit tests and a `quality_report.py` check, as in the test plan.

### Step 1 - Entity pre-pass: dates and numbers (fixes most of section 2)
* New `app/nlu/entities.py`: `extract(text) -> (clean_text, entities)`. Dates: today, tomorrow, tonight, weekend, weekday names, "next/this
  <weekday>", "in N days/hours", "on 5 nov", Roman Urdu `aaj`/`kal`/`parson`. Numbers in words: "fifteen", "a hundred", "square root of", "times",
  "plus", "divided by".
* Entities reach tools as optional inputs (`Input(type="date")`, `when`): weather/forecast/news use them; tools that do not declare one just
  never see them. Phrases keep working unchanged because the extractor removes the date words first: `weather next monday in karachi`
  -> `weather in karachi` + `when=monday`.
* Missing slot after extraction asks, not fails: `weather tomorrow` -> "Which place?" and remembers `when=tomorrow`.
* **Done when:** every date/number gap in `tests/corpus/intents.py` passes, `lahore`/`karachi` slots never contain date words (new property
  test over all phrases x date words), engine p95 still < 25 ms.

### Step 2 - Synonym and abbreviation table
* `app/nlu/lexicon.py`: one reviewed table (`temp->temperature`, `rs->pkr`, `pls/plz->please`, `u->you`, `info->information`, `bucks->dollars`,
  `msg->message`...) applied in `variants()` before matching; tools can contribute entries via `Tool(..., synonyms={...})` so a new tool never
  edits core. Port the old branch's `typos`/`abbreviations` lists as the seed.
* **Done when:** `temp in lahore`, `what is the temp in dubai` route to weather; a collision test proves a synonym never changes the meaning
  of a message that already matched (corpus accuracy and false positives unchanged).

### Step 3 - Ambiguity and confidence
* Expose `Decision.confidence` (0-1, derived from specificity and margin to the runner-up) and `Decision.alternatives`.
* Thresholds: `>= 0.7` act; `0.4-0.7` with a clear runner-up -> ask "Did you mean *A* or *B*?" (buttons on platforms that support them);
  `< 0.4` -> the existing suggestion/fallback path. Per-feature override (`Tool.feature(..., min_confidence=...)`) for risky actions.
* Log `confidence` in the structured log line; `quality_report.py` plots the distribution and lists low-confidence answers that users
  accepted (good) or abandoned (add phrases).
* **Done when:** thin-margin cases from the report either disappear or ask; no regression in corpus accuracy; asking rate on the corpus < 3%.

### Step 4 - Multi-intent
* Split on `and` / `then` / `also` / `,` / `;` only when *both* halves independently match a feature (or one half is a follow-up of the other),
  limited to 2 intents per message to bound cost and reply length; otherwise treat as one message (so `fish and chips`, `pizza or sushi` and
  `lahore and karachi` keep working).
* Execute sequentially, join replies with a divider; if the second fails, still send the first. Shared entity: `weather in lahore and time`
  -> the second inherits `lahore`.
* **Done when:** the multi-intent corpus (new `MULTI` section) passes, single-intent accuracy and false positives are unchanged, and a
  scenario test covers one half failing.

### Step 5 - Grow the real-message corpus (continuous)
* Every week: `scripts/unmatched.py list` -> decide -> `corpus` -> tests -> `review`. Target: 500 real labelled messages before any LLM
  or heavier NLU is considered; track accuracy on the real subset separately from the synthetic one.
* Anonymise before sharing a corpus: chat ids are already hashed; strip names/numbers from texts with a small scrubber.

## 4. Non-goals for now
* A general question-answering model; open questions ("who invented the telephone") stay on the roadmap as a search/Wikipedia fallback.
* Statistical intent classifiers or embeddings. They become interesting only after the corpus is large enough to train and evaluate them,
  and would plug in behind the existing `IntentEngine` interface, measured against the same corpus.

## 5. Where the code is
| Piece | File |
|---|---|
| Engine, variants, scoring, `explain()` | `app/intent/rule_based.py` |
| Decision / engine interface | `app/intent/decision.py` |
| Router (pending, follow-ups, repeats, fallback) | `app/smart.py`, `app/replies.py` |
| Declarative tool metadata | `app/core/schemas.py`, `app/core/tool.py`, `tools/*/tool.py` |
| Corpus + gaps | `tests/corpus/intents.py` |
| Improvement inbox | `app/inbox.py`, `scripts/unmatched.py` |
| Report | `scripts/quality_report.py` |
