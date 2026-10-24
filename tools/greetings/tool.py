"""Greetings and small talk: time-aware hellos, salam, thanks, goodbyes, "who are you". Replies adapt to the hour and to repeats."""
import random
import time
from datetime import datetime

from app.core.schemas import Input
from app.core.tool import Tool

tool = Tool("greetings", title="Greetings", emoji="👋", description="Say hi, thanks or goodbye, or ask who I am")

REPEAT_WINDOW = 600                       # seconds: greet again within this and Rory says "again"
_last: dict[str, float] = {}              # chat -> when we last greeted it (in memory, like all chat context)
HINT = "Send *help* to see what I can do."


def daypart(hour: int) -> str:
    return "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 17 else "evening" if 17 <= hour < 22 else "night"


def _now() -> datetime:
    return datetime.now()


def _seen_recently(chat_id: str) -> bool:
    now = time.monotonic()
    again = now - _last.get(chat_id, -REPEAT_WINDOW * 2) < REPEAT_WINDOW
    if len(_last) > 1000:                 # keep memory bounded
        _last.clear()
    _last[chat_id] = now
    return again


GREET = {"morning": ["Good morning! ☀️", "Morning! ☀️ Hope your day starts well."],
         "afternoon": ["Good afternoon! 🌤️", "Hey, good afternoon! 🌤️"],
         "evening": ["Good evening! 🌆", "Hey, good evening! 🌆"],
         "night": ["Hey, still up? 🌙", "Hello, night owl! 🌙"]}
AGAIN = ["Hey again! 👋", "Hi again! 😄", "Back already? 👋 I'm here."]


@tool.feature(
    "hello", description="Say hi",
    phrases=["hi", "hello", "hey", "hey there", "hi there", "hello there", "yo", "hola", "sup", "wassup", "what's up", "whats up",
             "howdy", "hiya", "heya", "greetings", "hi rory", "hello rory", "hey rory", "hi again", "hello again", "hey again"],
    examples=["hi", "hello there"])
async def hello(ctx):
    if _seen_recently(ctx.chat_id):
        return random.choice(AGAIN)
    return f"{random.choice(GREET[daypart(_now().hour)])} I'm Rory. {HINT}"


@tool.feature(
    "salam", description="Islamic greeting",
    phrases=["salam", "salaam", "assalamualaikum", "assalamu alaikum", "assalam o alaikum", "assalam alaikum", "as salamu alaykum",
             "as salam alaykum", "aoa", "slm", "peace be upon you"],
    examples=["assalamualaikum", "salam"])
async def salam(ctx):
    _seen_recently(ctx.chat_id)
    return "Wa alaikum assalam wa rahmatullahi wa barakatuh 🌙 " + HINT


@tool.feature(
    "daypart", description="Good morning / afternoon / evening / night",
    phrases=["good {part}", "good {part} rory", "{part}"],
    examples=["good morning", "good night"],
    inputs={"part": Input(required=True, pattern="morning|afternoon|evening|night")})
async def part_greeting(ctx, part):
    _seen_recently(ctx.chat_id)
    part = part.lower()
    actual = daypart(_now().hour)
    if part == "night":
        return "Good night! 🌙 Sleep well."
    if part == actual or (part == "evening" and actual == "night"):
        return f"Good {part}! {random.choice(['😊', '👋'])} {HINT}"
    return f"Good {part}! 😄 (It's {actual} here, but the thought counts.)"


@tool.feature(
    "thanks", description="Say thanks",
    phrases=["thanks", "thank you", "thx", "ty", "thanks a lot", "thank you so much", "many thanks", "thanks rory", "thank you rory",
             "shukriya", "jazakallah", "jazak allah", "jazakallah khair", "jazak allah khair"],
    examples=["thanks", "thank you so much"])
async def thanks(ctx):
    return random.choice(["😊 Anytime! Ask me anything else.", "You're welcome! 🙌", "Happy to help! 😄"])


@tool.feature(
    "how_are_you", description="Ask how I am",
    phrases=["how are you", "how are you doing", "how r u", "how are u", "how is it going", "how's it going", "hows it going",
             "how do you do", "how have you been", "you good"],
    examples=["how are you", "how's it going"])
async def how_are_you(ctx):
    return random.choice(["😎 Running at full speed! What would you like to know?", "Doing great, thanks for asking! 😄 What can I do for you?"])


@tool.feature(
    "who_are_you", description="Ask who I am",
    phrases=["who are you", "what are you", "your name", "what is your name", "what's your name", "whats your name",
             "are you a bot", "are you real", "are you human", "tell me about yourself", "introduce yourself"],
    examples=["who are you", "what's your name"])
async def who_are_you(ctx):
    return ("🤖 I'm *Rory* — a little help, wherever you chat. No AI guesswork, just real tools: weather, conversions, "
            "Wikipedia, Quran, games and more. Send *help* to see them.")


@tool.feature(
    "bye", description="Say goodbye",
    phrases=["bye", "goodbye", "good bye", "see you", "see ya", "see you later", "later", "cya", "take care", "bye bye", "bye rory",
             "khuda hafiz", "allah hafiz"],
    examples=["bye", "see you later"])
async def bye(ctx):
    _last.pop(ctx.chat_id, None)
    return random.choice(["👋 Bye! Come back any time.", "See you soon! 👋", "Take care! 🌟"])


@tool.feature(
    "praise", description="Say something nice",
    phrases=["i love you", "love you", "you are great", "you are awesome", "you are smart", "you are the best", "you're great",
             "you're awesome", "you're the best", "good bot", "nice bot", "great bot", "well done"],
    examples=["good bot", "you are awesome"])
async def praise(ctx):
    return random.choice(["🥰 Aww, thanks! Now go ask me something.", "😊 You're too kind!", "Thank you! 🙌 That made my day."])
