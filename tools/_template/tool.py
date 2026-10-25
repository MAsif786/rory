"""Copy this folder to tools/<name>/ and rename `tool` below to match. Folders starting with _ are ignored.

CHECKLIST (the tests do most of the checking: `pytest -q`)
  1. phrases      the ways people ask. {name} marks an input; give it a pattern= so it cannot swallow whole sentences.
  2. examples     at least two; each must route to this feature (tests/test_tools_nlu.py checks).
  3. negatives    messages that merely mention your keywords and must NOT trigger the tool.
  4. synonyms     other words people say for the words your phrases use. DO NOT guess: let WordNet suggest, then review:

         .venv/bin/python scripts/suggest_synonyms.py --download      # first time only (about 10 MB, into data/nltk_data)
         .venv/bin/python scripts/suggest_synonyms.py template         # candidates for this tool, from its own phrases
         .venv/bin/python scripts/suggest_synonyms.py --words greet    # or for specific words

     Keep only what a user would really say for exactly that thing (the script prints the meaning it matched). Paste the result into
     `Tool(..., synonyms={...})` below. Rules the registry enforces: single lowercase words, the target must appear in one of your
     phrases, no two tools may disagree. Synonyms are only a fallback and still have to match a declared phrase.
  5. dates        want "tomorrow" / "next monday" understood? Declare an input named `when` (see tools/weather): the engine lifts the
                  date out of the message first and hands it to you ("when": "next monday"; nlu/entities.days_ahead() turns it into a day count).
  6. corpus       add 3 lines to tests/corpus/intents.py (a plain one, a noisy one, and a near-miss to NEGATIVE) and a fixture for any
                  endpoint to tests/api_fixtures.py. Messages your tool cannot serve are logged to the improvement inbox for you.
"""
from app.core.schemas import Followup, Input
from app.core.tool import Tool

tool = Tool("template", title="Template", emoji="🧩", description="What this tool does",
            synonyms={"greeting": "greet"})   # reviewed output of scripts/suggest_synonyms.py: {word users say: word my phrases use}


@tool.feature(
    "greet",                                     # becomes "template.greet"
    description="Greets someone by name",
    phrases=["greet {name}"],
    keywords=[],
    examples=["greet sara", "greet ali"],
    negatives=[],
    inputs={"name": Input(required=True, pattern=r"[A-Za-z' -]{2,30}")},        # pattern: a name, not a whole sentence
    followups=[Followup(phrases=["and {name}"], overrides=["name"])],
)
async def greet(ctx, name):
    return f"Hello {name.title()}!"
