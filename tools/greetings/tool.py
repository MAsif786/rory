"""Greetings and small talk: time-aware hellos, salam, thanks, goodbyes, "who are you". Replies adapt to the hour and to repeats."""
import random
from datetime import datetime

from app.core.schemas import Input
from app.core.tool import Tool

tool = Tool("greetings", category="chat", hidden=True, title="Greetings", emoji="👋", description="Small talk", synonyms={"farewell": "bye", "gratitude": "thanks", "cheerio": "bye", "adieu": "goodbye", "adios": "goodbye", "sayonara": "goodbye", "hullo": "hello",
                      "arrivederci": "goodbye", "goodby": "goodbye", "thankyou": "thanks", "thnx": "thanks", "thanx": "thanks", "tnx": "thanks"})

REPEAT_WINDOW = 600                       # seconds: greet again within this and Rory says "again"
_last: dict[str, tuple[float, str]] = {}  # chat -> (when, which greeting) we last answered (in memory, like all chat context)
HINT = "Send *help* to see what I can do."


def daypart(hour: int) -> str:
    return "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 17 else "evening" if 17 <= hour < 22 else "night"


def _now() -> datetime:
    return datetime.now()


def _recall(chat_id: str, key: str, now: float) -> str:
    """Remember this greeting and say how it relates to the last one: "" (fresh), "again" (a greeting soon after one),
    or "same" (the very same greeting repeated)."""
    when, last_key = _last.get(chat_id, (-REPEAT_WINDOW * 2, ""))
    if len(_last) > 1000:                 # keep memory bounded
        _last.clear()
    _last[chat_id] = (now, key)
    if now - when >= REPEAT_WINDOW:
        return ""
    return "same" if key == last_key else "again"


GREET = {"morning": ["Good morning! ☀️", "Morning! ☀️ Hope your day starts well."],
         "afternoon": ["Good afternoon! 🌤️", "Hey, good afternoon! 🌤️"],
         "evening": ["Good evening! 🌆", "Hey, good evening! 🌆"],
         "night": ["Hey, still up? 🌙", "Hello, night owl! 🌙"]}
AGAIN = ["Hey again! 👋", "Hi again! 😄", "Back already? 👋 I'm here."]
SAME = ["😄 You already said that! Hi again.", "We've done this one already 😄 What can I help with?",
        "Hello hello again! 👋 Still here — what do you need?"]


@tool.feature(
    "hello", description="Say hi",
    phrases=["hi", "hello", "hey", "hey there", "hi there", "hello there", "yo", "hola", "sup", "wassup", "what's up", "whats up",
             "howdy", "hiya", "heya", "greetings", "hi rory", "hello rory", "hey rory", "hi again", "hello again", "hey again"],
    examples=["hi", "hello there"])
async def hello(ctx):
    if seen := _recall(ctx.chat_id, "hello", ctx.now):
        return random.choice(SAME if seen == "same" else AGAIN)
    return f"{random.choice(GREET[daypart(_now().hour)])} I'm Rory. {HINT}"


@tool.feature(
    "salam", description="Islamic greeting",
    phrases=["salam", "salaam", "assalamualaikum", "assalamu alaikum", "assalam o alaikum", "assalam alaikum", "as salamu alaykum",
             "as salam alaykum", "aoa", "slm", "peace be upon you", "salaam alaikum", "salam alaikum", "salam alaykum", "assalam u alaikum",
             "assalamu alaikum wa rahmatullah", "assalam o alaikum wa rahmatullah"],
    examples=["assalamualaikum", "salam"])
async def salam(ctx):
    seen = _recall(ctx.chat_id, "salam", ctx.now)
    if seen == "same":
        return "Wa alaikum assalam again 🌙 How can I help?"
    return "Wa alaikum assalam wa rahmatullahi wa barakatuh 🌙" + ("" if seen else " " + HINT)


@tool.feature(
    "daypart", description="Good morning / afternoon / evening / night",
    phrases=["good {part}", "good {part} rory", "{part}"],
    examples=["good morning", "good night"],
    inputs={"part": Input(required=True, pattern="morning|afternoon|evening|night")})
async def part_greeting(ctx, part):
    part = part.lower()
    seen = _recall(ctx.chat_id, f"daypart:{part}", ctx.now)
    actual = daypart(_now().hour)
    if seen == "same":
        return random.choice([f"😄 You already wished me good {part}! Good {part} again.", f"Good {part} to you too, again! 😄"])
    if part == "night":
        return "Good night! 🌙 Sleep well."
    if part == actual or (part == "evening" and actual == "night"):
        return f"Good {part}! {random.choice(['😊', '👋'])} {HINT}"
    return f"Good {part}! 😄 (It's {actual} here, but the thought counts.)"


@tool.feature(
    "thanks", description="Say thanks",
    phrases=["thanks", "thank you", "thx", "ty", "thanks a lot", "thank you so much", "many thanks", "thanks rory", "thank you rory",
             "thank u", "thanks u", "thanks so much", "thank you very much", "thanks a ton", "thx u", "shukriya", "jazakallah", "jazak allah", "jazakallah khair", "jazak allah khair"],
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
             "are you a bot", "are you real", "are you human", "tell me about yourself", "introduce yourself", "what can you do",
             "what do you do", "what can you help with", "how can you help me"],
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
    _last.pop(ctx.chat_id, None)               # a goodbye ends the conversation, so the next hello is fresh
    return random.choice(["👋 Bye! Come back any time.", "See you soon! 👋", "Take care! 🌟"])


POSITIVE = {"good", "fine", "great", "well", "ok", "okay", "alright", "happy", "excited", "awesome", "amazing", "blessed", "better"}
MOOD_REPLIES = {
    "positive": ["Glad to hear it! 😊 What can I do for you?", "Nice! 😄 Anything I can help with today?", "Great to hear! 🙌 Ask me anything."],
    "tired": ["Sounds like you could use some rest 😴 I'm here if you need something quick first."],
    "low": ["Sorry you're feeling that way 💙 Want a distraction? Try *tell me a joke* or *play hangman*."],
    "bored": ["Let's fix that! 🎮 Try *play hangman*, *tell me a joke* or *flip a coin* — or send *games*."],
    "sick": ["Get well soon! 🤒 Rest up and drink plenty of water."],
    "hungry": ["🍕 I can't cook, but I can decide for you: try *choose between pizza or sushi*."],
    "busy": ["No rush 🙂 I'm here whenever you need me."],
}
MOOD_GROUP = {**{m: "positive" for m in POSITIVE}, "tired": "tired", "sleepy": "tired", "sad": "low", "lonely": "low", "stressed": "low",
              "angry": "low", "nervous": "low", "bored": "bored", "sick": "sick", "hungry": "hungry", "busy": "busy"}
_MOOD = "|".join(sorted(MOOD_GROUP, key=len, reverse=True))


@tool.feature(
    "mood", description="Tell me how you feel (I'm good, I'm tired...)",
    phrases=["i'm {mood}", "im {mood}", "i am {mood}", "i feel {mood}", "i'm feeling {mood}", "feeling {mood}", "i'm {mood} today",
             "i am doing {mood}", "doing {mood}", "all good", "not bad", "fine thanks", "good thanks", "alhamdulillah", "alhamdulillah good",
             "i'm doing great", "i'm doing well", "i'm doing good"],
    examples=["I'm good", "i'm tired"],
    inputs={"mood": Input(default="good", pattern=_MOOD)})
async def mood(ctx, mood):
    return random.choice(MOOD_REPLIES[MOOD_GROUP.get(mood.lower(), "positive")])


@tool.feature(
    "praise", description="Say something nice",
    phrases=["i love you", "love you", "you are great", "you are awesome", "you are smart", "you are the best", "you're great",
             "you're awesome", "you're the best", "good bot", "nice bot", "great bot", "well done"],
    examples=["good bot", "you are awesome"])
async def praise(ctx):
    return random.choice(["🥰 Aww, thanks! Now go ask me something.", "😊 You're too kind!", "Thank you! 🙌 That made my day."])
