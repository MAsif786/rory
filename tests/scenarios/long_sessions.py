"""Long, realistic sessions (15-30 turns): topic hopping, follow-up chains, interruptions, silences, outages, games, and the NLU layer
(synonyms, typos, dates spoken or in Roman Urdu, spoken maths, out-of-scope requests) woven through, the way real people chat.

What these catch that short scenarios cannot: state leaking between topics, a follow-up attaching to the wrong earlier answer, context that
survives (or dies) at the wrong moment, and behaviour that only appears after many turns."""
from app.core.context import REPEAT_TTL, SESSION_TTL, TURN_TTL
from tests.scenarios.dsl import Scenario, T
from tests.scenarios.games import secret

MORNING = Scenario("session: a morning routine (greeting, weather chain, news, thanks, synonyms, goodbye)", [
    T("assalamualaikum", has="Wa alaikum assalam"),
    T("what's the weather in lahore", has="Lahore", http="Lahore"),
    T("and tomorrow", has="(tomorrow)", http="Lahore"),                              # follow-up 1: only the day changes
    T("what about karachi", has="(tomorrow)", http="Karachi"),                       # follow-up 2: the place changes, the day is kept
    T("and the day after tomorrow", has="Then:", http="Karachi"),                    # follow-up 3: still Karachi
    T("today's news", has=["Top headlines", "1️⃣"]),
    T("3", has=["🔗", "Story 3"], no_http=True),                                     # the number opens story 3 without refetching
    T("tell me a jest", any_of=["😂", "scarecrow"], http="random_joke"),             # tool synonym: jest -> joke
    T("thanks", any_of=["Anytime", "welcome", "Happy"]),
    T("any tidings today", has="Top headlines"),                                     # tool synonym: tidings -> news
    T("flip a coin", any_of=["Heads", "Tails"]),
    T("farewell", any_of=["Bye", "soon", "care"]),                                   # tool synonym: farewell -> bye
    T("hello", has="Rory"),                                                          # the goodbye reset the greeting memory: a fresh hello
])

TOPIC_HOPPING = Scenario("session: hopping between topics and coming back", [
    T("weather in lahore", http="Lahore"),
    T("news about mars", has="News: mars"),
    T("what about cricket", has="News: cricket", http="cricket"),                    # "what about" follows the LAST topic (news), not weather
    T("100 usd to pkr", has="28,050.00"),
    T("what about 10", has="2,805.00", http="USD"),                                  # ... and now the last topic is currency
    T("and in eur", http="EUR", has="10.00 USD"),
    T("who is einstein", has="Albert Einstein"),
    T("what about newton", http="Newton"),                                           # wiki follow-up
    T("weather in paris", http="Paris"),
    T("and tomorrow", has="(tomorrow)", http="Paris"),                               # weather is the last topic again: Paris, not Lahore
    T("capital of japan", has="Tokyo"),
    T("what about france", http="france", has="Tokyo"),
    T("and tomorrow", has="Tomorrow for what?", no_http=True, lacks="Paris"),        # a country has no "tomorrow": not looked up, and the old weather is not revived
])

CONVERSIONS = Scenario("session: conversions, spoken maths, synonyms and typos in one chat", [
    T("100 usd to pkr", has="28,050.00"),
    T("what about 25", has="7,012.50"),
    T("how much is a dollar in rupees", has="280.50"),
    T("5 km in miles", has="3.107 mi"),
    T("what's fifteen plus four", has="*19*"),
    T("square root of 144", has="*12*"),
    T("what is twenty percent of fifty", has="*10*"),
    T("temp in dubai", has="Lahore", http="dubai"),                                  # core synonym temp -> temperature (fixture always answers Lahore)
    T("wether in karachi", http="karachi"),                                          # typo repaired
    T("and tomorrow", has="(tomorrow)", http="karachi"),                             # follow-up of a synonym/typo-matched weather answer
    T("exchange 50 euros to dollars", http="EUR"),                                   # tool synonym: exchange -> convert
    T("25*8", has="*200*"),
    T("2^10", has="*1024*"),
    T("whats the climate in oslo", http="oslo"),                                     # tool synonym: climate -> weather
])

CLARIFY_DETOURS = Scenario("session: open questions, detours and abandoned questions", [
    T("weather", has="Which place?"),
    T("tell me a joke", any_of=["😂", "scarecrow"], lacks="Which place"),            # a different request cancels the open question
    T("lahore", lacks="Lahore, Pakistan"),                                           # ...so a stray "lahore" is NOT silently the answer any more
    T("weather", has="Which place?"),
    T("multan", http="multan"),                                                      # the real answer
    T("and tomorrow", has="(tomorrow)", http="multan"),
    T("weather tomorrow", has="Which place?"),                                       # date known, place missing
    T("quetta", has="(tomorrow)", http="quetta"),                                    # the remembered day is applied to the answer
    T("choose", has="Which options"),
    T("100 usd to pkr", has="28,050.00", lacks="I pick"),                            # detour from a pending question to a lookup
    T("tea or coffee", any_of=["tea", "coffee"], lacks="I pick:*tea or coffee"),     # no stale question is left over: this is a plain message now
    T("choose between tea or coffee", has="I pick"),
])

GAME_WITH_INTERRUPTIONS = Scenario("session: a game interrupted by menus, help and other tools", [
    T("weather in lahore", http="Lahore"),
    T("play hangman", session="hangman"),
    T("e", has="Lives", session="hangman"),
    T("menu", has="Home", session="hangman"),                                        # menus never end a game
    T("help weather", has="weather.current", session="hangman"),
    T("a", has="Lives", session="hangman"),
    T("weather in lahore", session="hangman", lacks="Lahore, Pakistan"),             # inside a game, tool phrases are just game input
    T("hello", session="hangman", has="Lives"),                                      # inside hangman a single word is a guess (a deliberate rule: the game wins)
    T("t", has="Lives", session="hangman"),
    T("quit", has="Game ended", session=None),
    T("weather in lahore", wait=REPEAT_TTL + 1, has="Lahore, Pakistan", http="Lahore"),   # a minute later: normal service, fetched afresh
    T("and tomorrow", has="(tomorrow)", http="Lahore"),
    T("play guess", session="guess"),
    T("50", pre=secret(77), session="guess", any_of=["higher", "lower", "Go"]),
    T("stop", has="Game ended", session=None),
    T("and tomorrow", has="(tomorrow)"),                                             # follow-up context survived the games in between
])

SILENCES = Scenario("session: silences expire context (follow-ups, questions, games, greetings)", [
    T("weather in lahore", http="Lahore"),
    T("and tomorrow", has="(tomorrow)"),
    T("and tomorrow", wait=TURN_TTL + 1, has=["Tomorrow for what?", "lost track"], no_http=True),   # five minutes later it has nothing to attach to
    T("weather in karachi", http="Karachi"),
    T("play guess", session="guess"),
    T("ping", wait=SESSION_TTL + 1, eq="pong 🏓", session=None),                      # an abandoned game expired by itself
    T("weather", has="Which place?"),
    T("lahore", wait=TURN_TTL + 1, lacks="Lahore, Pakistan"),                        # an abandoned question expired too
    T("hello", has="Rory"),
    T("hello", any_of=["already", "again", "Still here"]),                           # inside the greeting window
    T("hello", wait=700, has="Rory"),                                                # after 10+ minutes it is a fresh hello again
    T("capital of japan", has="Tokyo"),
    T("capital of japan", has="Same as a moment ago", no_http=True),
    T("capital of japan", wait=REPEAT_TTL + 1, http="japan", lacks="Same as"),       # after a minute the answer is fetched again
])

OUTAGE_SESSION = Scenario("session: an outage in the middle of a conversation", [
    T("weather in lahore", http="Lahore"),
    T("who is einstein", has="Albert Einstein"),
    T("weather in karachi", fail="connect", has="couldn't reach"),
    T("and tomorrow", has="Tomorrow for what?"),                                      # the failed weather was not remembered; the last good answer was a wiki lookup
    T("25*8", has="*200*"),                                                           # pure tools keep working during the outage
    T("flip a coin", any_of=["Heads", "Tails"]),
    T("hello", has="Rory"),
    T("play hangman", session="hangman"),
    T("e", session="hangman", has="Lives"),                                           # a game survives the outage
    T("quit", session=None),
    T("weather in karachi", fail=None, http="Karachi", has="Lahore, Pakistan"),       # recovered
    T("and tomorrow", has="(tomorrow)", http="Karachi"),
])

REPEATS_IN_FLOW = Scenario("session: repeating and re-asking inside a longer chat", [
    T("who is einstein", has="Albert Einstein"),
    T("who is einstein", has="Same as a moment ago", no_http=True),
    T("hello", has="Rory"),
    T("who is einstein", http="Einstein", lacks="Same as"),                           # something else happened in between: asked afresh
    T("tell me a joke", any_of=["😂", "scarecrow"]),
    T("tell me a joke", any_of=["😂", "scarecrow"], lacks="Same as"),                 # randomness is never "reused"
    T("blah blah blah blah blah blah", has="didn't get that"),
    T("blah blah blah blah blah blah", has="Still not sure"),
    T("order me a pizza", has="can't place orders"),
    T("order me a pizza", has="still something I can't do"),
    T("what can you do", has="Rory"),
])

NLU_MIX = Scenario("session: out-of-scope requests, typos, politeness and Roman Urdu together", [
    T("please could you tell me the weather in lahore", http="Lahore"),
    T("kal ka mausam karachi", has="(tomorrow)", http="karachi"),                     # Roman Urdu date
    T("play some music", has="can't play music", lacks="Hangman"),
    T("bitcoin price", has="Prices"),
    T("set an alarm for 7", has="Reminders"),
    T("tell me a gag", any_of=["😂", "scarecrow"]),                                  # synonym
    T("fun fact", has="Did you know"),
    T("khabrein", has="Top headlines"),                                               # Roman Urdu headlines
    T("shukriya", any_of=["Anytime", "welcome", "Happy"]),
    T("is it going to rain tomorrow in murree", has="(tomorrow)", http="murree"),
    T("I'm good", any_of=["Glad", "Nice", "Great"]),
    T("i'm bored", has="Games"),
    T("play higher or lower", session="highlow"),
    T("quit", session=None),
    T("cheerio", any_of=["Bye", "soon", "care"]),                                     # synonym
])

LONG_SESSIONS = [MORNING, TOPIC_HOPPING, CONVERSIONS, CLARIFY_DETOURS, GAME_WITH_INTERRUPTIONS, SILENCES, OUTAGE_SESSION, REPEATS_IN_FLOW, NLU_MIX]
