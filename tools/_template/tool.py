"""Copy this folder to tools/<name>/ and rename `tool` below to match. Folders starting with _ are ignored."""
from app.core.schemas import Followup, Input
from app.core.tool import Tool

tool = Tool("template", title="Template", emoji="🧩", description="What this tool does")   # name must equal the folder name


@tool.feature(
    "greet",                                     # becomes "template.greet"
    description="Greets someone by name",
    phrases=["greet {name}"],
    keywords=[],
    examples=["greet sara"],
    negatives=[],
    inputs={"name": Input(required=True)},
    followups=[Followup(phrases=["and {name}"], overrides=["name"])],
)
async def greet(ctx, name):
    return f"Hello {name.title()}!"
