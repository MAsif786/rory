# Language understanding: what Rory has, what it lacks, and the plan

Status as of 2026-10-25 (second revision: entity pre-pass, synonyms and out-of-scope handling are now built). Rory is rule-based (no
LLM): every tool declares `phrases`, `keywords`, `negatives`, typed `inputs`, `followups` and `synonyms`; one small engine
(`app/intent/rule_based.py`) matches messages against them. Roadmap context: `docs/ROADMAP.md` (Phase 3); measuring: `docs/TEST_PLAN.md`.

## 1. Status at a glance

| Capability | Status | How it works | Remaining gap |
|---|---|---|---|
| Test corpus of real messages | **Yes (small)** | `tests/corpus/intents.py` (~180 labelled messages incl. a `REAL` section from live chats, 45 chatter lines that must not match, argument checks, `GAPS` backlog). The improvement inbox (`data/unmatched.jsonl`, `scripts/unmatched.py`) collects new real messages. | Needs production traffic; few real messages so far. |
| Spelling normalization | **Yes** | politeness stripped, de-elongation ("hii"), typo repair (5+ letters, similarity >= 0.9), optional apostrophes, case/punctuation ignored; negatives also see the original text. | Short-word typos ("oll", "wtr") only get "Did you mean...?". |
| Synonyms | **Yes** | `app/nlu/lexicon.py` (core chat abbreviations: `temp`, `abt`, `u`...) + each tool's `Tool(..., synonyms={...})`, merged. Used only as a fallback or a *challenger* (it must beat the direct match's rank) and only when the rewritten message matches a declared phrase; max 2 words rewritten; words some phrase already uses are never rewritten. Candidates are generated at **development time** with WordNet (`scripts/suggest_synonyms.py`) and **reviewed by a human**; the bot never loads WordNet. | A reviewed table is small (grow it per tool); no dictionary-word guard for typo repair yet. |
| Context across a long chat | **Yes** | follow-ups track the *last* topic (not the first), a failed answer is never remembered, expiry per kind (follow-up 5 min, game 10, repeat 1, greeting 10), and a bare date with nothing to attach to says "Tomorrow for what?" | Groups: a follow-up needs no mention only from the person Rory just answered (see below). |
| Entities: dates | **Yes** | `app/nlu/entities.py` lifts "tomorrow", "next monday", "the weekend", "in 3 days", "day after tomorrow", Roman Urdu `kal`/`parson`/`aaj` out *before* matching; a feature that declares an input named `when` receives it (weather does; others can adopt). The rewrite is only trusted when the matched feature takes a `when`. | Only weather uses it so far; no clock times ("at 5pm"), no calendar dates ("5 nov"). |
| Entities: numbers & maths in words | **Yes** | "fifteen plus four" -> `15 + 4`, "square root of 144" -> `sqrt(144)`, "twenty percent of fifty" -> `20 percent of 50`; only trusted when the matched feature is the calculator. | Fractions, ordinals, decimals in words. |
| Entities: currencies | **Yes** | codes and names (`dollars`, `rupees`...), amounts with separators. | ~20 currencies, no crypto. |
| Entities: cities | **Partial** | captured from a phrase slot and validated by the geocoder. | No gazetteer; a city is not recognised without a trigger phrase. |
| Clarification questions | **Partial** | missing required input -> question (`Input.ask`), next message answers it, a different request cancels it; near-misses -> "Did you mean X?". | Nothing asks "A or B?" when two features tie. |
| Out-of-scope detection | **Yes** | requests no tool serves ("order me a pizza", "set an alarm", "bitcoin price") are answered honestly ("I can't place orders. I can help with weather, news...") instead of "I didn't get that", and filed by capability (`orders`, `reminders`, `music`, `prices`...) so demand can be counted. Statements that merely mention a topic ("I love music") are not mistaken for requests. | The category list is hand-written (`CAPABILITY_GAPS` in `app/replies.py`). |
| Confidence thresholds | **No** | ranking is internal `(kind, specificity)`; fixed cutoffs for typo repair and suggestions. | No exposed confidence, no per-tool thresholds. |
| Multi-intent | **No** | one message -> one intent (+ follow-ups). | "weather in lahore and time in lahore" still merges into one slot. |

## 2. Evidence (probe, before -> after)

| Message | Before | Now |
|---|---|---|
| `weather next monday in karachi` | place = `next monday in karachi` | place = `karachi`, when = `next monday`, answered for that day |
| `forecast for the weekend in dubai` | place = `the weekend in dubai` | place = `dubai`, when = `weekend` |
| `weather tomorrow` | nothing | asks "Which place?" and remembers tomorrow |
| `kal ka mausam lahore` | gap | tomorrow's weather for Lahore |
| `what's fifteen plus four` / `square root of 144` | wiki lookup / gap | calculator: 19 / 12 |
| `temp in lahore`, `what is the temp in dubai` | nothing / Wikipedia | weather (core synonym `temp`) |
| `tell me a jest`, `any tidings today`, `farewell` | nothing | joke, headlines, goodbye (tool synonyms) |
| `who is the writer of dune` | Wikipedia | book tool (the synonym reading is stronger than the direct one) |
| `list of jokes or facts` | country facts for "list of jokes or" | not a country |
| `order me a pizza`, `bitcoin price` | "I didn't get that" | "I can't place orders..." / "Prices aren't available yet...", logged as demand |
| `weather in lahore and time in lahore` | place = `lahore and time in lahore` | **unchanged** (multi-intent, step 4) |
| `100 usd to pkr and eur` | nothing | **unchanged** |

## 3. How synonyms work (design and safety)

* **Where entries come from.** (1) Core abbreviations that mean the same everywhere (`app/nlu/lexicon.py`). (2) Per-tool `synonyms={}`,
  produced like this: run `scripts/suggest_synonyms.py <tool>`: for each word the tool's phrases use, WordNet proposes words
  of the same *most common* sense (`gag -> joke`), filtered by a symmetry check (the candidate must itself mean the tool word in its own most
  common sense; this drops `word -> news` and `reserve -> book`), by "already a word some tool uses", and by ambiguity (a candidate that
  could mean two of your words is reported, not suggested). A person then keeps the safe ones and adds chat words WordNet cannot know.
* **Why not WordNet at runtime.** Measured: 1.6 s load and +177 MB, and every sense of every word ("book" -> Bible, bankroll; "play" ->
  45 synonyms) which would turn "book a flight" or "roll up my sleeves" into tool calls; it also has no `pls`, `bro`, `mausam`, `khabrein`.
  The shipped table is tiny and reviewed, so the runtime cost is a dictionary lookup.
* **Guardrails (all tested in `tests/test_nlu_layer.py`).** Fallback/challenger only; the rewritten text must match a declared phrase; at
  most two substitutions; known words are never rewritten; registry rejects synonyms that point at a word the tool does not use, that
  contradict another tool or the core table, or that are not single lowercase words; and 61 chatter/out-of-scope messages must never be
  rewritten into a tool call.
* **Tested from the data, not by hand** (`tests/test_synonyms_auto.py`): every synonym x every phrase containing its target must read exactly like the original,
  and the whole corpus must match identically with the layer disabled (explicit allow-list of deliberate upgrades). Dates and synonyms combine
  ("what's the climate tomorrow in oslo" -> weather, when=tomorrow). Current additions beyond the first batch: `select->choose`, `pct->percent`,
  `math/maths->calc`, `headline->headlines`, `arrivederci/goodby->goodbye`, chat spellings `thnx/thanx/tnx/thankyou->thanks`.
* **Measured value.** On 25 paraphrases the WordNet-only idea understood 8 (4 via synonyms), with 0 wrong answers on 61 chatter/out-of-scope
  messages. The synonym layer is a safety-first widening, not a magic wand: most paraphrase failures were *phrase shape*, which the
  entity pre-pass and new phrases fixed. Growth should come from real messages (inbox) rather than bigger synonym lists.

## 4. Remaining plan

1. **Ambiguity and confidence.** Expose `Decision.confidence` and `alternatives`; ask "Did you mean *A* or *B*?" when two features score
   close (per-feature threshold for risky actions); log confidence. *Done when* thin-margin cases in the report ask or disappear and corpus
   accuracy is unchanged.
2. **Multi-intent.** Split on `and` / `then` / `also` only when both halves independently match (or one is a follow-up of the other), max 2
   intents, so `fish and chips`, `pizza or sushi`, `Trinidad and Tobago` keep working; run sequentially, a failed second half never blocks the
   first. *Done when* a `MULTI` corpus section passes and single-intent accuracy is unchanged.
3. **Dictionary guard for typo repair** (optional). A ~40k-word list (300 KB, 1 µs per lookup) so real words are never "repaired" and shorter
   typos (`oll`, `wtr`) can be repaired safely; benchmarked in the discussion that led here (pyspellchecker's dictionary: 0.1 s load, +44 MB; its
   own `correction()` is 55 ms per word and must not be used).
4. **More `when` consumers.** News ("news from yesterday"), clock ("time tomorrow in tokyo" is not meaningful), reminders (Phase 4).
5. **Grow the real-message corpus** (continuous): `scripts/unmatched.py list` -> decide -> `corpus` -> tests -> `review`. Target 500 real labelled
   messages before any heavier NLU is considered; track accuracy on the real subset separately.

## 5. Non-goals for now
* A general question-answering model; open questions ("who invented the telephone") stay on the roadmap as a search/Wikipedia fallback.
* Statistical intent classifiers or embeddings, until the corpus is large enough to train and evaluate them; they would plug in behind the
  existing `IntentEngine` interface and be measured against the same corpus.

## 6. Where the code is
| Piece | File |
|---|---|
| Engine: variants, scoring, pre-tiers, synonym challenger, `explain()` | `app/intent/rule_based.py` |
| Decision (incl. `via`, `entities`) | `app/intent/decision.py` |
| Dates, spoken maths | `app/nlu/entities.py` |
| Core synonyms, rewrite rules | `app/nlu/lexicon.py` |
| WordNet suggestion logic (dev time) / CLI | `app/nlu/suggest.py` / `scripts/suggest_synonyms.py` |
| Router, fallback, out-of-scope | `app/smart.py`, `app/replies.py` |
| Tool metadata (`synonyms`, `when`) | `app/core/tool.py`, `app/core/schemas.py`, `tools/*/tool.py` |
| Corpus + gaps | `tests/corpus/intents.py` |
| Improvement inbox / demand ranking | `app/inbox.py`, `scripts/unmatched.py` |
| Report | `scripts/quality_report.py` |
