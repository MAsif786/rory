# Rory

*A little help, wherever you chat.*

A modular, rule-based chat companion that connects messaging platforms with useful tools, everyday assistance, and games — without requiring an LLM.
Rory is extensible and platform-independent, with pluggable tools, built-in games, and a replaceable intent engine.

Today Rory talks through [WAHA](https://waha.devlike.pro) (WhatsApp): messages arrive at `POST /webhook` and replies go back as text.
Drop a folder into `tools/` and Rory picks it up — see [docs/ADDING_A_TOOL.md](docs/ADDING_A_TOOL.md). Routing lives in `app/smart.py`; send *help* to see what's installed.

```bash
cp .env.example .env              # set WAHA_API_KEY
docker compose up -d              # WAHA on :3000 (webhook already points at the bot) — scan the QR code
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --port 8000 --reload --reload-dir app --reload-dir tools   # restarts on code changes
.venv/bin/python -m pytest                      # offline, ~12 s
.venv/bin/python scripts/quality_report.py     # how well does Rory understand, and what to improve next
```

Messages Rory could not answer are saved to `data/unmatched.jsonl`; review them with `scripts/unmatched.py list` ([how it fits in](docs/TEST_PLAN.md)).

**Writing a tool?** Copy `tools/_template/` ([guide](docs/ADDING_A_TOOL.md)). To find the other words people use for yours, let WordNet suggest synonyms while you develop (development only; the bot never loads it) and review them:
`.venv/bin/python scripts/suggest_synonyms.py --download` (once), then `scripts/suggest_synonyms.py <tool>`.

Language understanding: what exists and what is planned is in [docs/NLU_CAPABILITIES.md](docs/NLU_CAPABILITIES.md); the roadmap is in [docs/ROADMAP.md](docs/ROADMAP.md).

**Secure the webhook (recommended before exposing the bot beyond localhost):** WAHA can sign every webhook. Put one random secret in `.env` as
`WHATSAPP_HOOK_HMAC_KEY=<long random string>` (WAHA reads this file through docker compose; the bot reads the same variable), restart both, and the bot
rejects anything not signed with it (HTTP 401). Until it is set the bot logs a warning at startup. Details and an optional token mode: `.env.example`.

Load and abuse testing: `scripts/stress_test.py all --quick` (local bot + fake WAHA, never touches WhatsApp).

Testing is described in [docs/TEST_PLAN.md](docs/TEST_PLAN.md) (intent corpus, follow-ups, conversations, failure matrix, live API checks).

## What Rory can do

Send *help* in chat to see this list, or *help <tool>* for details.

| Tool | Try |
|---|---|
| Weather | `weather in lahore` · `forecast for tokyo` |
| Currency · Units · Calculator | `100 usd to pkr` · `5 km in miles` · `15% of 200` · `sqrt(144)` |
| Clock | `time in Tokyo` |
| Wikipedia · Movies · Books · Countries | `who is Einstein` · `movie Inception` · `who wrote Dune` · `capital of France` |
| GitHub · IP lookup · Link preview | `repo tiangolo/fastapi` · `8.8.8.8` · paste any URL, then `tech` / `security` / `links` |
| Quran | `2:255` · `ayat al kursi in urdu` · `verses about patience` · `surah rahman` · `tafsir 2:255` |
| News · Web search | `today's news` · `news about cricket` · `google best pizza` (needs a Google key) |
| Fun · Dice | `tell me a joke` · `flip a coin` · `roll 2d6` · `choose pizza or sushi` |
| Games | `play blackjack` / `dungeon` / `guess` / `hangman` / `highlow` / `memory` / `quiz` / `rps` / `trivia` / `ttt` |

Optional `.env` keys: `BOT_CONTACT`, `TMDB_API_KEY` (movie ratings), `GITHUB_TOKEN` (rate limits), `NEWS_COUNTRY` (news edition, e.g. `PK`), `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` (web search).

The earlier full version (tools, intent engines, games) lives on the `modular-architecture` branch.
