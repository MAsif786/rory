"""Jokes and fun facts."""
import random
import re

from app.core.schemas import Input, UserError
from app.core.tool import Tool
from app.wikipedia import cut, page_url, summary

tool = Tool("fun", title="Fun", emoji="😂", description="Jokes and fun facts")


@tool.feature(
    "joke", description="A random joke",
    phrases=["joke", "a joke", "tell me a joke", "tell me another joke", "another joke", "one more joke", "give me a joke",
             "make me laugh", "say something funny", "tell me something funny", "got any jokes"],
    keywords=["joke", "jokes"], examples=["tell me a joke", "make me laugh"],
    negatives=["no joke", "not a joke", "joking", "joke's on"])
async def joke(ctx):
    r = await ctx.services.http.get("https://official-joke-api.appspot.com/random_joke")
    r.raise_for_status()
    j = r.json()
    return f"😂 {j['setup']}\n\n👉 {j['punchline']}"


@tool.feature(
    "fact", description="A random fun fact",
    phrases=["fact", "a fact", "fun fact", "random fact", "tell me a fact", "tell me a fun fact", "tell me a random fact",
             "give me a fact", "another fact", "one more fact", "did you know", "something interesting", "tell me something interesting"],
    examples=["tell me a fact", "fun fact"])
async def fact(ctx):
    r = await ctx.services.http.get("https://uselessfacts.jsph.pl/api/v2/facts/random", params={"language": "en"})
    r.raise_for_status()
    return f"🤓 *Did you know?*\n{r.json()['text']}"


@tool.feature(
    "fact_about", description="A fun fact about a topic (did you know something about the moon)",
    phrases=["fact about {topic}", "a fact about {topic}", "fun fact about {topic}", "tell me a fact about {topic}", "tell me a fun fact about {topic}",
             "did you know something about {topic}", "did you know about {topic}", "did you know anything about {topic}",
             "tell me something interesting about {topic}", "something interesting about {topic}", "interesting facts about {topic}",
             "interesting fact about {topic}", "give me a fact about {topic}"],
    examples=["did you know something about the moon", "fun fact about octopuses"],
    inputs={"topic": Input(required=True, pattern=r"(?!(?:i|me|my|you|your|we|us|our)\b)[^\n]{2,60}", ask="🤓 A fact about what?")})
async def fact_about(ctx, topic):
    page = await summary(ctx.services.http, topic, missing=f"🤓 I couldn't find a fact about *{topic}*. Try another topic.")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", " ".join((page.get("extract") or "").split())) if len(s) > 25]
    if not sentences:
        raise UserError(f"🤓 I couldn't find a fact about *{topic}*. Try another topic.")
    fact = random.choice(sentences[1:4] or sentences[:1])             # skip the dry opening definition when there is more to say
    return f"🤓 *Did you know?* ({page['title']})\n{cut(fact, 300)}\n\n🔗 {page_url(page)}"
