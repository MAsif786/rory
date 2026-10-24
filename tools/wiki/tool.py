"""Wikipedia summaries: who is X, tell me about X, define X."""
from app.core.schemas import Followup, Input
from app.core.tool import Tool
from app.wikipedia import cut, page_url, summary

tool = Tool("wiki", title="Wikipedia", emoji="📚", description="Look anything up on Wikipedia")

# a topic is the name of something: not a sentence about "me" or "you"
TOPIC = r"(?!(?:i|me|my|you|your|yourself|we|us|our|it|this|that|there|the time|the weather)\b)[\w'.&, -]{2,60}"


@tool.feature(
    "lookup", repeat="reuse", description="Wikipedia summary of a topic (who is Einstein, tell me about volcanoes)",
    phrases=["who is {topic}", "who was {topic}", "who are {topic}", "what is {topic}", "what is a {topic}", "what is an {topic}",
             "what are {topic}", "what was {topic}", "tell me about {topic}", "tell me more about {topic}", "explain {topic}",
             "define {topic}", "meaning of {topic}", "history of {topic}", "information on {topic}", "information about {topic}",
             "look up {topic}", "learn about {topic}", "describe {topic}", "wiki {topic}", "wikipedia {topic}"],
    keywords=["wikipedia", "wiki"],
    examples=["who is Einstein", "tell me about volcanoes"],
    negatives=["weather", "forecast", "temperature", "time in", "joke", "fact", "movie", "film", "news", "headlines", "country", "capital of",
               "population of", "github", "repo"],
    inputs={"topic": Input(required=True, pattern=TOPIC, ask="📚 What should I look up?")},
    followups=[Followup(phrases=["what about {topic}", "how about {topic}", "and {topic}"], overrides=["topic"])])
async def lookup(ctx, topic):
    page = await summary(ctx.services.http, topic)
    return f"📚 *{page['title']}*\n{cut(page.get('extract'), 550)}\n\n🔗 {page_url(page)}"
