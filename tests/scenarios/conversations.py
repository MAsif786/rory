"""Multi-turn conversations: follow-ups, clarifications, repeats, greetings, help, unknown words and outages."""
from app.core.context import REPEAT_TTL, TURN_TTL
from tests.scenarios.dsl import Scenario, T

FOLLOWUPS = [
    Scenario("weather: switch city keeps the feature", [T("weather in lahore", has="Lahore"), T("what about karachi", http="Karachi", has="Lahore"),
                                                         T("how about tokyo", http="Tokyo")]),
    Scenario("forecast: switch city stays a forecast", [T("forecast for tokyo", has="5-day"), T("what about dubai", http="Dubai", has="5-day")]),
    Scenario("fresh request beats a follow-up", [T("weather in lahore"), T("forecast for paris", has="5-day", http="Paris")]),
    Scenario("currency: change the amount, keep the pair", [T("100 usd to pkr", has="28,050.00"), T("what about 10", http="'base': 'USD'", has="2,805.00")]),
    Scenario("currency: change the target, keep the amount", [T("100 usd to pkr"), T("and in eur", http="EUR", has="100.00 USD")]),
    Scenario("wiki: next topic", [T("who is einstein", has="Albert Einstein"), T("what about newton", http="Newton")]),
    Scenario("movie: next title", [T("movie inception", http="inception"), T("what about interstellar", http="interstellar")]),
    Scenario("book: next title", [T("who wrote dune", has="Frank Herbert"), T("how about emma", http="emma")]),
    Scenario("country: next country", [T("capital of japan", has="Tokyo"), T("what about france", http="france")]),
    Scenario("clock: next city", [T("time in tokyo", http="Tokyo"), T("what about london", http="London")]),
    Scenario("news: reply a number to open a story (no refetch)", [
        T("today's news", has=["Top headlines", "1️⃣", "Reply *1*–*5*"], lacks="https://"),
        T("2", has=["🔗", "https://news.google.com"], no_http=True), T("open 4", has="Story 4", no_http=True)]),
    Scenario("news: out-of-range pick is a friendly error", [T("top headlines"), T("link 9", has="from 1 to 5")]),
    Scenario("news: a new topic resets the story pick", [T("news about mars", has="News: mars"), T("1", has="🔗"),
                                                          T("what about football", has="News: football", http="football")]),
    Scenario("follow-up context expires", [T("weather in lahore"), T("what about karachi", wait=TURN_TTL + 1, has="lost track", lacks="Karachi, ")]),
    Scenario("failed answer is not remembered as context", [T("weather in lahore", fail="connect", has="couldn't reach"),
                                                             T("what about karachi", fail=None, has="lost track", no_http=True)]),
]

AGAIN = [
    Scenario("again: a coin flipped over and over, in every wording", [
        T("flip a coin", any_of=["Heads", "Tails"]), T("flip", any_of=["Heads", "Tails"], lacks="know"), T("toss again", any_of=["Heads", "Tails"]),
        T("again", any_of=["Heads", "Tails"]), T("one more", any_of=["Heads", "Tails"]), T("another one", any_of=["Heads", "Tails"]),
        T("flip it", any_of=["Heads", "Tails"]), T("more", any_of=["Heads", "Tails"], lacks="Same as")]),
    Scenario("again: dice keep their notation", [T("roll 3d6", has="3 dice"), T("again", has="3 dice"), T("roll again", has="You rolled a"), T("roll", has="You rolled a"),
                                                  T("roll d20", has="(20-sided)"), T("one more", has="(20-sided)")]),
    Scenario("again: a pick is made from the same options", [T("choose between tea or coffee", has="I pick"), T("again", any_of=["tea", "coffee"], has="I pick"),
                                                             T("another", any_of=["tea", "coffee"], has="I pick")]),
    Scenario("again: a fresh joke / fact every time, never 'same as a moment ago'", [
        T("tell me a joke", http="random_joke"), T("another one", http="random_joke", lacks="Same as"), T("again", http="random_joke"),
        T("tell me a fact", http="uselessfacts"), T("one more", http="uselessfacts", lacks="Same as"), T("did you know something about the moon", http="moon"),
        T("again", http="moon")]),
    Scenario("again: live data is asked afresh", [T("weather in lahore", http="Lahore"), T("again", http="Lahore", lacks="Same as"),
                                                  T("100 usd to pkr", http="frankfurter"), T("again", http="frankfurter", lacks="Same as"), T("today's news", has="Top headlines"),
                                                  T("again", has="Top headlines", http="news.google.com")]),
    Scenario("again: with nothing to repeat it says so", [T("again", has="Again what?"), T("one more time", has="Again what?"), T("repeat", has="Again what?"),
                                                           T("flip a coin"), T("again", any_of=["Heads", "Tails"]),
                                                           T("again", wait=TURN_TTL + 1, has="Again what?")]),
    Scenario("again: follows the LAST answer, not an older one", [T("tell me a joke"), T("flip a coin", any_of=["Heads", "Tails"]), T("again", any_of=["Heads", "Tails"], lacks="👉"),
                                                                   T("roll 2d6"), T("again", has="2 dice")]),
    Scenario("again: a game is not interrupted by it", [T("play guess", session="guess"), T("again", session="guess")]),
]

CLARIFY = [
    Scenario("weather: asks for the place, then uses the answer", [T("weather", has="Which place?"), T("multan", http="multan", has="Lahore")]),
    Scenario("calculator: asks for the expression", [T("calculate", has="What should I calculate"), T("2*8", has="*16*")]),
    Scenario("dice choose: asks for options", [T("choose", has="Which options"), T("tea or coffee", has="I pick")]),
    Scenario("github repo: asks which repo", [T("repo", has="Which repo"), T("tiangolo/fastapi", has="fastapi")]),
    Scenario("news topic: asks, then answers", [T("news about the", has="News about what"), T("cricket", http="cricket", has="News: cricket")]),
    Scenario("pending question expires", [T("weather", has="Which place?"), T("lahore", wait=TURN_TTL + 1, lacks="Lahore")]),
    Scenario("a different request cancels the pending question", [T("weather", has="Which place?"), T("100 usd to pkr", has="28,050.00", lacks="Weather"),
                                                                    T("lahore", lacks="Today")]),
    Scenario("invalid answer gets a clear message", [T("roll 99d6", has="Between 1 and 20")]),
]

REPEATS = [
    Scenario("lookup repeated: reused, no second API call", [T("who is einstein", has="Albert Einstein"),
                                                             T("who is einstein", has="Same as a moment ago", no_http=True),
                                                             T("Who is Einstein?", has="a few times", no_http=True)]),
    Scenario("lookup repeated after a minute: asked again", [T("capital of japan", http="japan"), T("capital of japan", wait=REPEAT_TTL + 1, http="japan", lacks="Same as")]),
    Scenario("random things always re-run", [T("tell me a joke", lacks="Same as"), T("tell me a joke", lacks="Same as", http="random_joke")]),
    Scenario("a different request in between resets the repeat", [T("capital of japan"), T("flip a coin"), T("capital of japan", lacks="Same as", http="japan")]),
    Scenario("unknown message repeated: second reply differs", [T("the quick brown fox jumps over the lazy dog", has="didn't get that"),
                                                                 T("the quick brown fox jumps over the lazy dog", has="Still not sure")]),
]

GREETINGS = [
    Scenario("first hello introduces Rory", [T("hi", has=["Rory", "help"])]),
    Scenario("hello twice: noticed", [T("hello", has="Rory"), T("hello", any_of=["already", "again", "Still here"], lacks="*help*")]),
    Scenario("different greeting soon after: 'again'", [T("hello"), T("good morning", any_of=["Good morning", "again"])]),
    Scenario("bye resets, next hello is fresh", [T("hello"), T("bye", any_of=["Bye", "soon", "care"]), T("hello", has="Rory")]),
    Scenario("salam gets the proper reply, repeats are noticed", [T("assalamualaikum", has="Wa alaikum assalam"), T("salam", has="again")]),
    Scenario("thanks / small talk", [T("thanks", any_of=["Anytime", "welcome", "Happy"]), T("how are you", has="?"), T("who are you", has="Rory")]),
    Scenario("greeting never shows the menu", [T("hi", lacks="Home"), T("hello", lacks="Home")]),
]

HELP = [
    Scenario("help lists tools; help <tool> details; help <feature>", [
        T("help", has=["Home", "Weather", "Games"]), T("help weather", has="weather.current"), T("help weather.current", has=["Needs:", "Try:"]),
        T("help nope", has="No group, tool or feature called")]),
    Scenario("menu aliases", [T("menu", has="Home"), T("!help", has="Home"), T("/menu", has="Home"), T("start", has="Home")]),
    Scenario("games menu", [T("games", has=["Games", "play blackjack"]), T("play a game", has="Games"), T("i'm bored", has="Games")]),
    Scenario("help works mid-game and keeps the game", [T("play hangman", session="hangman"), T("menu", has="Home", session="hangman"),
                                                          T("help all", session="hangman")]),
    Scenario("what can you do", [T("what can you do", has="Rory")]),
]

UNKNOWN = [
    Scenario("small talk is acknowledged", [T("super", lacks="didn't get that", has="help"), T("ok", lacks="didn't get that"), T("lol", lacks="didn't get that")]),
    Scenario("a short unknown word offers Wikipedia", [T("zorblax", has=["I don't know *zorblax*", "tell me about zorblax"])]),
    Scenario("a typo is repaired, a bigger one gets a suggestion", [T("wether in lahore", has="Lahore"), T("wtr in lahore", has="Did you mean")]),
    Scenario("a long sentence shows real examples", [T("the quick brown fox jumps over the lazy dog", has=["didn't get that", "Try"])]),
    Scenario("ping", [T("ping", eq="pong 🏓")]),
]

OUTAGES = [
    Scenario("upstream down: clear message, then recovers", [T("weather in lahore", fail="connect", has="couldn't reach that service"),
                                                              T("weather in lahore", fail=None, has="Lahore")]),
    Scenario("upstream timeout", [T("who is einstein", fail="timeout", has="couldn't reach")]),
    Scenario("upstream 500", [T("capital of japan", fail="500", has="couldn't reach")]),
    Scenario("upstream 404 is not a crash", [T("movie inception", fail="404", any_of=["couldn't reach", "No movie found"])]),
    Scenario("upstream returns the wrong shape: generic error, no leak", [T("weather in lahore", fail="malformed", any_of=["Something went wrong", "Couldn't find a place"], lacks="unexpected")]),
    Scenario("pure tools work during an outage", [T("25*8", fail="connect", has="*200*"), T("flip a coin"), T("roll 2d6"), T("hello", has="Rory")]),
    Scenario("outage mid-game does not end the game", [T("play hangman", fail="connect", session="hangman"), T("e", session="hangman")]),
]

REAL_CHATS = [
    Scenario("real chat: feelings, a topical fact, and 'tell about'", [
        T("I'm good", any_of=["Glad", "Nice", "Great"], lacks=["don't know", "Wikipedia"]),
        T("Did you know something about moon", has="Did you know?", lacks="didn't get that", http="moon"),
        T("Tell about moon", has="📚", lacks="didn't get that", http="moon")]),
    Scenario("first-person statements are acknowledged, not looked up", [
        T("I just got home", has="Thanks for telling me", lacks="Wikipedia"), T("my phone is slow", has="Thanks for telling me")]),
    Scenario("moods get fitting answers", [T("i'm tired", has="rest"), T("im bored", has="Games"), T("i'm hungry", has="pizza"), T("i feel sad", has="Sorry")]),
]

ALL = [*FOLLOWUPS, *AGAIN, *CLARIFY, *REPEATS, *GREETINGS, *HELP, *UNKNOWN, *OUTAGES, *REAL_CHATS]
