# Adding a tool

1. Copy `tools/_template/` to `tools/<name>/` (the folder name **is** the tool name; `_`-prefixed folders are ignored).
2. Edit `tool.py`. It must define `tool = Tool("<name>")`. No core code changes needed.
3. Run `python -m pytest`. A bad tool is rejected at startup with a clear log line; other tools still load.

## Answer tool
```python
tool = Tool("weather")

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
| `inputs` | `Input(type="text"\|"int"\|"float", required, default, choices)`. |
| handler | `async def handler(ctx, **inputs)`; arg names equal the `inputs` keys. Returns a string. |
| errors | Raise freely: the user sees a generic message, details go to the log. |
| HTTP | Use `ctx.services.http`, don't build your own client. |

Startup checks: placeholders have inputs, follow-ups use real inputs, each feature has an example, no two features share a phrase, a game has both a session feature and a `@tool.session` handler.

## Routing order
active game → direct command (`ping`, `help`) → greeting → answer to the bot's question → intent engine (fresh match beats follow-up; clarify asks; none falls back).
Follow-up context and pending questions expire after 5 minutes.
