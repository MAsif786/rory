# Adding a tool

1. Copy `tools/_template/` to `tools/<name>/` (the folder name **is** the tool name; `_`-prefixed folders are ignored).
2. Edit `tool.py`. It must define `tool = Tool("<name>")`. No core code changes needed.
3. Run `python -m pytest`. A bad tool is rejected at startup with a clear log line; other tools still load.

## Where it shows up in help
`help` is organised into groups, not one long list. Choose yours with `category=`: `everyday` (weather, news, money, time, maths), `knowledge` (Wikipedia, countries,
books, movies), `islamic`, `web` (GitHub, IP, links, search), `entertainment` (jokes, dice), `chat` (greetings and small talk). Games are the `games` group
automatically. A tool with no (or an unknown) category appears under **More**, so it is never hidden, but a test fails until the tool picks a group.
Give the tool a clear `title` and a SHORT `description` (2-4 words, at most 30 characters; a test enforces it): the group page shows both, plus up to three of your
`examples`. An example that looks like a link (`https://example.com`) is never displayed in help (chat apps turn it into a preview); it still counts for the tests.
`hidden=True` keeps a tool out of the help pages (greetings use it) while it keeps working, and `help <name>` still opens it.
```python
tool = Tool("tarot", category="entertainment", title="Tarot", emoji="🔮", description="Draw a card")
```
Users reach it with `help` (the groups), `help entertainment` (the group, also by aliases like `fun`-words), `help tarot` (its features), or `help all` (a compact index).

## Answer tool
```python
tool = Tool("weather", title="Weather", emoji="🌦️", description="Current weather and forecasts")  # title/emoji/description show in help

@tool.feature("current", description="Current weather",
    phrases=["weather in {place}"], keywords=["weather"],
    examples=["weather in lahore"], negatives=["whether or not"],
    inputs={"place": Input(required=True), "day": Input(default="today", choices=("today", "tomorrow"))},
    followups=[Followup(phrases=["what about {place}"], overrides=["place"]),
               Followup(phrases=["and tomorrow"], sets={"day": "tomorrow"})])
async def current(ctx, place, day):
    return f"Weather in {place} ({day}): ..."
```

## "Again" / "one more" for random or live answers
Coin flips, dice, picks, jokes, facts and live data (weather, news, currency) should answer "again", "one more", "another one", "more" by repeating the request
with the same arguments (a roll of 3d6 stays 3d6, a pick keeps its options). Add the ready-made follow-up:
```python
from app.core.schemas import AGAIN
@tool.feature("flip", phrases=["flip a coin", "flip", "toss again"], examples=["flip a coin"], followups=[AGAIN])
```
Bare forms people type for the tool itself ("flip", "roll") belong in `phrases`; "again" with nothing to repeat (the context expired) gets "Again what?" from the router.
The auto-derived follow-up tests check that `AGAIN` keeps every argument, so a new tool using it is covered the day it is added.

## Synonyms: let WordNet suggest, you review
People say "gag" for "joke" and "tidings" for "news". Declare such words on the tool, and the engine (as a fallback, and only when the rewritten
message matches one of your declared phrases) reads them as your word:
```python
tool = Tool("fun", title="Fun", emoji="😂", description="Jokes and fun facts", synonyms={"gag": "joke", "jest": "joke"})
```
Do not invent the list: generate candidates from WordNet at development time (the bot itself never loads WordNet):
```bash
.venv/bin/python scripts/suggest_synonyms.py --download     # once: fetches ~10 MB into data/nltk_data (nltk is in requirements-dev.txt)
.venv/bin/python scripts/suggest_synonyms.py fun            # candidates from the words your phrases use
.venv/bin/python scripts/suggest_synonyms.py --words joke   # or for specific words
```
The output shows each candidate with the meaning it matched and a ready `synonyms={...}` line. **Review it**: WordNet knows every sense
of a word (`tending -> care`, `amercement -> fine` are technically synonyms and useless). Keep what a user would really type for exactly that
thing; add chat words WordNet cannot know (`pls`, `bro`, Roman Urdu) by hand. Candidates are already filtered to the most common sense and
by a symmetry check; `--word-senses 2 --candidate-senses 2` loosens that if you want more to choose from.

Rules the registry and tests enforce: single lowercase words; the target word must appear in one of the tool's phrases or keywords; a word
some tool's phrase already uses is never rewritten; two tools cannot disagree about a synonym or redefine one of the core chat
abbreviations (`app/nlu/lexicon.py`: `temp`, `abt`, `u`...); at most two words of a message are rewritten; and
`tests/test_nlu_layer.py` proves synonyms never turn chatter or out-of-scope requests into tool calls.

## Dates and spoken numbers
Declare an input named `when` and the engine understands "tomorrow", "next monday", "the weekend", "in 3 days", "kal" for you: the date is
lifted out of the message first, so it can never end up inside another slot, and arrives as `when="next monday"`. Use
`app.nlu.entities.days_ahead(when)` to turn it into a day count and `describe(when)` for wording ("Monday 26 Oct"); a message with a date but
no place still asks "Which place?" and remembers the date. Spoken maths ("fifteen plus four", "square root of 144") is rewritten for the
calculator automatically.

## Requests Rory cannot serve
A request no tool and no synonym matches is answered honestly ("I can't place orders. I can help with weather, news...") and filed in the
improvement inbox by capability (`scripts/unmatched.py stats` ranks the missing capabilities users ask for: that is your tool roadmap).
To teach Rory a new capability category, add a line to `CAPABILITY_GAPS` in `app/replies.py`, or better, build the tool.

## Game tool
```python
tool = Tool("trivia")

@tool.feature("start", kind="session", phrases=["play trivia"], examples=["play trivia"])
async def start(ctx): return SessionStart(state={"score": 0}, reply="First question: ...")

@tool.session
async def on_message(ctx, state, message):
    if message == "hello": return PassThrough()     # not for the game
    if message == "done":  return Finish("Final score: ...")
    return Continue(state, "Next question: ...")
```
`stop` / `quit` always ends a game; it expires after 10 idle minutes.

## Rules
| Part | Notes |
|---|---|
| `phrases` / `keywords` | At least one. `{place}` marks an argument and needs an entry in `inputs`. |
| `examples` | Required (at least one); also shown by `help`. |
| `negatives` | Messages that must not match. |
| `inputs` | `Input(type="text"\|"int"\|"float", required, default, choices, pattern, ask)`. `pattern` is a regex a `{placeholder}` must match (e.g. `r"\d+"`); it keeps free-text phrases like `{amount} {base} to {quote}` from matching ordinary sentences. `ask` is the question when a required input is missing. |
| handler | `async def handler(ctx, **inputs)`; arg names equal the `inputs` keys. Returns a string. |
| `UserError` | `raise UserError("📍 Couldn't find that place")` shows the message to the user. Any other exception shows a generic message and is logged. |
| errors | Raise freely: the user sees a generic message, details go to the log. |
| HTTP | Use `ctx.services.http`, don't build your own client. |

Startup checks: placeholders have inputs, follow-ups use real inputs, each feature has an example, no two features share a phrase, a game has both a session feature and a `@tool.session` handler.

## Routing order
`menu`/`help` (always, even mid-game) → active game → direct command (`ping`) → answer to the bot's question → intent engine (fresh match beats follow-up; clarify asks; none falls back).
Follow-up context and pending questions expire after 5 minutes.

## Games
A game is a small class with `start()`, `handle(text)` and a `finished` property; `handle` returns `""` when a message isn't for the game (it then falls through to routing). The class is the session state, and `game_tool()` builds the tool, including "play <name>" phrases from its aliases:
```python
# tools/hangman/tool.py
from app.games import game_tool
from .game import Hangman
tool = game_tool(Hangman, emoji="🔤")
```
See `app/games.py` and any `tools/*/game.py`.

## Tests
`tests/test_tools_nlu.py` checks every installed tool: each `examples` entry must route to its own feature, `negatives` must never match it, and ordinary chatter must match nothing. Run it after adding a tool.
