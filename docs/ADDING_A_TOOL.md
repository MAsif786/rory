# Adding a tool

1. Copy `tools/_template/` to `tools/<name>/` (the folder name **is** the tool name; `_`-prefixed folders are ignored).
2. Edit `tool.py`. It must define `tool = Tool("<name>")`. No core code changes needed.
3. Run `python -m pytest`. A bad tool is rejected at startup with a clear log line; other tools still load.

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
