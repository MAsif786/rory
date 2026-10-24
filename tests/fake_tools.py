WEATHER = '''
from app.core.schemas import Followup, Input
from app.core.tool import Tool

tool = Tool("weather")

@tool.feature("current",
    phrases=["weather in {place}", "is it raining in {place}"],
    keywords=["weather"],
    examples=["weather in lahore"],
    negatives=["whether or not"],
    inputs={"place": Input(required=True), "day": Input(default="today", choices=("today", "tomorrow"))},
    followups=[Followup(phrases=["what about {place}"], overrides=["place"]),
               Followup(phrases=["and tomorrow"], sets={"day": "tomorrow"})])
async def current(ctx, place, day):
    return f"{place} {day}"
'''

COUNTDOWN = '''
from app.core.schemas import Continue, Finish, PassThrough, SessionStart
from app.core.tool import Tool

tool = Tool("countdown")

@tool.feature("start", kind="session", phrases=["play countdown"], examples=["play countdown"])
async def start(ctx):
    return SessionStart(3, "3")

@tool.session
async def on_message(ctx, state, message):
    if message == "hello":
        return PassThrough()
    if state == 1:
        return Finish("liftoff")
    return Continue(state - 1, str(state - 1))
'''

BOOM = '''
from app.core.tool import Tool

tool = Tool("boom")

@tool.feature("go", phrases=["explode"], examples=["explode"])
async def go(ctx):
    raise RuntimeError("secret internal detail")
'''
