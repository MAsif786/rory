"""Jokes and fun facts."""
from app.core.tool import Tool

tool = Tool("fun", title="Fun", emoji="😂", description="Jokes and fun facts")


@tool.feature(
    "joke", description="A random joke",
    phrases=["joke", "a joke", "tell me a joke", "tell me another joke", "another joke", "one more joke", "give me a joke",
             "make me laugh", "say something funny", "tell me something funny", "got any jokes"],
    keywords=["joke", "jokes"], examples=["tell me a joke"])
async def joke(ctx):
    r = await ctx.services.http.get("https://official-joke-api.appspot.com/random_joke")
    r.raise_for_status()
    j = r.json()
    return f"😂 {j['setup']}\n\n👉 {j['punchline']}"


@tool.feature(
    "fact", description="A random fun fact",
    phrases=["fact", "a fact", "fun fact", "random fact", "tell me a fact", "tell me a fun fact", "tell me a random fact",
             "give me a fact", "another fact", "one more fact", "did you know", "something interesting", "tell me something interesting"],
    examples=["tell me a fact"])
async def fact(ctx):
    r = await ctx.services.http.get("https://uselessfacts.jsph.pl/api/v2/facts/random", params={"language": "en"})
    r.raise_for_status()
    return f"🤓 *Did you know?*\n{r.json()['text']}"
