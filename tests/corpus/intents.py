"""Labelled messages for intent detection: (text, expected feature or None). Add a line whenever a real message is misrouted.

Sections mirror how people actually type: plain, noisy (case/punctuation/spacing), wrapped in politeness, and near-misses
that must NOT trigger a tool. A message the engine cannot handle yet goes in GAPS (with the reason), not in CORPUS, so the
suite stays green and the backlog stays visible; when a gap gets fixed its test XPASSes and tells you to promote it."""

# --- plain: the canonical way to ask for each feature -----------------------------------------------------------------
PLAIN = [
    ("i'm good", "greetings.mood"), ("i am tired", "greetings.mood"), ("all good", "greetings.mood"),
    ("did you know something about the moon", "fun.fact_about"), ("fun fact about octopuses", "fun.fact_about"), ("tell about moon", "wiki.lookup"),
    ("weather in lahore", "weather.current"), ("what's the weather in karachi", "weather.current"), ("is it raining in london", "weather.current"),
    ("temperature in dubai", "weather.current"), ("forecast for tokyo", "weather.forecast"), ("weather next week in paris", "weather.current"),
    ("will it rain in murree", "weather.forecast"), ("100 usd to pkr", "currency.convert"), ("convert 50 euros to dollars", "currency.convert"),
    ("how much is 20 gbp in pkr", "currency.convert"), ("usd to eur", "currency.convert"), ("5 km in miles", "units.convert"),
    ("convert 20 celsius to fahrenheit", "units.convert"), ("2 kg to lb", "units.convert"), ("25*8", "calc.calc"), ("what is 12 + 30", "calc.calc"),
    ("sqrt(144)", "calc.calc"), ("2^10", "calc.calc"), ("15% of 200", "calc.percent"), ("what is 20 percent of 50", "calc.percent"),
    ("time in tokyo", "clock.time"), ("what time is it in london", "clock.time"), ("what time is it", "clock.time"),
    ("tell me a joke", "fun.joke"), ("another joke", "fun.joke"), ("tell me a fact", "fun.fact"), ("fun fact", "fun.fact"),
    ("flip a coin", "dice.flip"), ("heads or tails", "dice.flip"), ("roll a dice", "dice.roll"), ("roll 2d6", "dice.roll"),
    ("choose between pizza or sushi", "dice.choose"), ("pick pizza, sushi, tacos", "dice.choose"),
    ("who is einstein", "wiki.lookup"), ("tell me about volcanoes", "wiki.lookup"), ("what is photosynthesis", "wiki.lookup"),
    ("define entropy", "wiki.lookup"), ("movie inception", "movie.info"), ("is inception a good movie", "movie.info"),
    ("who wrote dune", "book.info"), ("book 1984", "book.info"), ("capital of france", "country.facts"), ("country japan", "country.facts"),
    ("population of brazil", "country.facts"), ("github fastapi", "github.search"), ("search github for telegram bot", "github.search"),
    ("repo tiangolo/fastapi", "github.repo"), ("8.8.8.8", "ipinfo.lookup"), ("ip 1.1.1.1", "ipinfo.lookup"),
    ("https://example.com", "link.peek"), ("summarize https://example.com", "link.peek"), ("2:255", "quran.verse"),
    ("quran 112:1-4 in urdu", "quran.verse"), ("ayat al kursi in urdu", "quran.kursi"), ("random verse", "quran.random"),
    ("verses about patience", "quran.search"), ("surah rahman", "quran.surah"), ("audio 1:1", "quran.audio"), ("recite surah yasin", "quran.surah_audio"),
    ("tafsir 2:255", "quran.tafsir"), ("today's news", "news.headlines"), ("top headlines", "news.headlines"), ("news about mars", "news.about"),
    ("pakistan news", "news.about"), ("google best pizza in lahore", "search.web"), ("search for python tutorials", "search.web"),
    ("hi", "greetings.hello"), ("hello there", "greetings.hello"), ("assalamualaikum", "greetings.salam"), ("good morning", "greetings.daypart"),
    ("thanks", "greetings.thanks"), ("how are you", "greetings.how_are_you"), ("who are you", "greetings.who_are_you"), ("bye", "greetings.bye"),
    ("good bot", "greetings.praise"), ("play blackjack", "blackjack.start"), ("play hangman", "hangman.start"), ("play tic tac toe", "ttt.start"),
    ("play rock paper scissors", "rps.start"), ("play trivia", "trivia.start"), ("play quiz", "quiz.start"), ("play dungeon", "dungeon.start"),
    ("play higher or lower", "highlow.start"), ("play number guess", "guess.start"), ("play memory challenge", "memory.start"),
]

# --- noisy: same intents with case, punctuation and spacing that real keyboards produce --------------------------------------
NOISY = [
    ("WEATHER IN LAHORE", "weather.current"), ("Weather in Lahore!", "weather.current"), ("weather   in   lahore", "weather.current"),
    ("  weather in lahore  ", "weather.current"), ("weather in lahore?", "weather.current"), ("weather in lahore.", "weather.current"),
    ("100 USD to PKR", "currency.convert"), ("100 Usd To Pkr!!", "currency.convert"), ("Who Is Einstein?", "wiki.lookup"),
    ("TELL ME A JOKE", "fun.joke"), ("Flip A Coin", "dice.flip"), ("PLAY HANGMAN", "hangman.start"), ("Play  Blackjack ", "blackjack.start"),
    ("Hello!", "greetings.hello"), ("HI", "greetings.hello"), ("Thanks!!", "greetings.thanks"), ("ASSALAMUALAIKUM", "greetings.salam"),
    ("Capital of France?", "country.facts"), ("TIME IN TOKYO", "clock.time"), ("Roll 2D6", "dice.roll"), ("TODAY'S NEWS", "news.headlines"),
    ("Github FastAPI", "github.search"), ("What's the weather in Karachi?", "weather.current"), ("5 KM in Miles", "units.convert"),
]

# --- polite / chatty wrappers around a clear request -------------------------------------------------------------------------
WRAPPED = [
    ("hey, what's the weather in lahore", "weather.current"), ("can you tell me a joke", "fun.joke"), ("please flip a coin", "dice.flip"),
    ("could you convert 100 usd to pkr", "currency.convert"), ("hi can you tell me the weather in karachi", "weather.current"),
    ("i want to play hangman", "hangman.start"), ("let's play blackjack", "blackjack.start"), ("tell me the news", "news.headlines"),
    ("show me the latest news", "news.headlines"), ("please tell me about volcanoes", "wiki.lookup"),
]

PROMOTED = [   # bare / repeat forms of random tools
    ("flip", "dice.flip"), ("toss", "dice.flip"), ("flip again", "dice.flip"), ("toss it", "dice.flip"), ("roll", "dice.roll"), ("roll again", "dice.roll"),   # reviewed synonym additions (see scripts/suggest_synonyms.py)
    ("thnx", "greetings.thanks"), ("thanx bro", "greetings.thanks"), ("select pizza or sushi", "dice.choose"), ("15 pct of 200", "calc.percent"),
    ("math 2+2", "calc.calc"), ("top headline", "news.headlines"), ("arrivederci", "greetings.bye"), ("what's the climate tomorrow in oslo", "weather.current"),   # promoted after the entity pre-pass (dates, spoken maths) and tool synonyms
    ("will i need an umbrella next monday in karachi", "weather.forecast"), ("square root of 144", "calc.calc"), ("what's 15 times 4", "calc.calc"),
    ("lahore ka mausam kaisa hai aaj", "weather.current"), ("kal ka mausam lahore", "weather.current"), ("weather tomorrow", "weather.current"),
    ("what's fifteen plus four", "calc.calc"), ("what is twenty percent of fifty", "calc.percent"), ("tell me a jest", "fun.joke"),
    ("any tidings today", "news.headlines"), ("farewell", "greetings.bye"), ("who is the writer of dune", "book.info"),
    ("exchange 100 dollars to rupees", "currency.convert"), ("what's the climate in lahore", "weather.current"),   # were gaps; fixed by input canonicalisation (typo repair, de-elongation, politeness stripping) or new phrases
    ("wether in lahore", "weather.current"), ("whats the wether in karachi", "weather.current"), ("hii", "greetings.hello"), ("heyyy", "greetings.hello"),
    ("thank u", "greetings.thanks"), ("salaam alaikum", "greetings.salam"), ("flip coin please", "dice.flip"), ("news please", "news.headlines"),
    ("time in new york right now", "clock.time"), ("is it going to rain tomorrow in karachi", "weather.forecast"), ("how hot is it in dubai", "weather.current"),
    ("what's 5 miles in km", "units.convert"), ("how many km in 5 miles", "units.convert"), ("tell me something about japan", "wiki.lookup"),
    ("what is happening in the world", "news.headlines"), ("play tictactoe", "ttt.start"), ("gimme a joke", "fun.joke"),
    ("what's the capital of pakistan", "country.facts"), ("100 dollars in rupees", "currency.convert"), ("will i need an umbrella tomorrow in karachi", "weather.forecast"),
    ("how much is a dollar in rupees", "currency.convert"), ("what's 20% of 150", "calc.percent"), ("throw dice", "dice.roll"), ("read quran 1:1", "quran.verse"),
    ("usd pkr rate", "currency.convert"), ("what can you do", "greetings.who_are_you"), ("lahore ka mausam kaisa hai", "weather.current"),
    ("aaj ka mausam", "weather.current"), ("mujhe khabrein batao", "news.headlines"), ("what are the headlines", "news.headlines"),
]

REAL = [   # taken from the live chat log
    ("I'm good", "greetings.mood"), ("Did you know something about moon", "fun.fact_about"), ("Tell about moon", "wiki.lookup"),
    ("im tired", "greetings.mood"), ("I'm hungry", "greetings.mood"), ("fine thanks", "greetings.mood"), ("alhamdulillah", "greetings.mood"),
]

# --- must NOT trigger any tool ------------------------------------------------------------------------------------------------
NEGATIVE = [
    "whether or not to go", "i don't know whether it will work", "good news", "bad news", "no news is good news", "movie night at my place",
    "book a flight to dubai", "i want to book a table", "bed time", "what time to eat", "let's meet at 5", "my phone number is 555-1234",
    "yes/no", "and/or", "can you help me with my homework", "see you tomorrow", "what do you think", "i'll roll up my sleeves", "lets play", "play",
    "the weather was terrible last week", "i have a coin collection", "my dice are broken", "the book was great", "i watched a movie yesterday",
    "that joke was bad", "thanks but no thanks to that idea", "random thoughts", "just testing", "what", "why", "ok then", "hmm interesting",
    "i'm going to the market", "im sorry", "i am a student", "i feel like pizza", "doing laundry", "one more time", "again", "another one", "more", "next", "who", "tell me", "convert", "play", "quran is a book", "the news was boring", "bye bye bye bye bye",
]

# --- messages that should ask a clarifying question (feature identified, an input missing) -------------------------------------
CLARIFY = [
    ("weather", "weather.current", "place"), ("what's the weather", "weather.current", "place"), ("forecast", "weather.forecast", "place"),
    ("calculate", "calc.calc", "expr"), ("choose", "dice.choose", "options"), ("repo", "github.repo", "repo"), ("link", "link.peek", "url"),
    ("tafsir", "quran.tafsir", "ref"),
]

# --- known gaps: realistic messages the engine does not handle yet (the improvement backlog) ---------------------------------
# (text, expected feature, why it fails / what would fix it). Strict xfail: when one starts passing the suite goes red until you
# move it into PLAIN/NOISY/WRAPPED, so the backlog never goes stale.
GAPS = [
    ("convert 100 dollars into rupees and euros", "currency.convert", "multiple quotes joined by 'and' (only commas are supported)"),
    ("who invented the telephone", "wiki.lookup", "open questions ('who invented/when was/how tall is'): needs a question-to-search fallback"),
    ("when was pakistan founded", "wiki.lookup", "open question"),
    ("how tall is mount everest", "wiki.lookup", "open question"),
    ("recommend a book like dune", "book.info", "recommendations are not a lookup: needs a different feature"),
    ("cricket scores", "news.about", "'<topic> scores' is not a news phrase; could be search.web"),
    ("bitcoin price", "search.web", "price/real-time queries have no tool (crypto/stocks tool)"),
]

# --- argument extraction: the feature AND what was captured (case of names/URLs must survive) ---------------------------------
ARGS = [
    ("weather next monday in karachi", "weather.current", {"place": "karachi", "when": "next monday"}),
    ("forecast for the weekend in dubai", "weather.forecast", {"place": "dubai", "when": "weekend"}),
    ("weather tomorrow in Karachi", "weather.current", {"place": "Karachi", "when": "tomorrow"}),
    ("what's fifteen plus four", "calc.calc", {"expr": "15 + 4"}), ("square root of 144", "calc.calc", {"expr": "sqrt(144)"}),
    ("tell about moon", "wiki.lookup", {"topic": "moon"}), ("did you know something about the moon", "fun.fact_about", {"topic": "the moon"}),
    ("i'm tired", "greetings.mood", {"mood": "tired"}),
    ("weather in Lahore", "weather.current", {"place": "Lahore"}), ("what's the weather in New York?", "weather.current", {"place": "New York"}),
    ("forecast for Tokyo", "weather.forecast", {"place": "Tokyo"}), ("100 usd to pkr", "currency.convert", {"amount": "100", "base": "usd", "quote": "pkr"}),
    ("convert 50 euros to dollars", "currency.convert", {"amount": "50", "base": "euros", "quote": "dollars"}),
    ("1,250.50 gbp in eur", "currency.convert", {"amount": "1,250.50", "base": "gbp", "quote": "eur"}),
    ("5 km in miles", "units.convert", {"value": "5", "src": "km", "dst": "miles"}), ("-3 c to f", "units.convert", {"value": "-3", "src": "c", "dst": "f"}),
    ("15% of 200", "calc.percent", {"pct": "15", "n": "200"}), ("2 + 2 * 3", "calc.calc", {"expr": "2 + 2 * 3"}),
    ("time in Asia/Karachi", "clock.time", {"place": "Asia/Karachi"}), ("roll 3d8", "dice.roll", {"dice": "3d8"}),
    ("choose between tea or coffee", "dice.choose", {"options": "tea or coffee"}), ("who is Marie Curie", "wiki.lookup", {"topic": "Marie Curie"}),
    ("movie The Matrix", "movie.info", {"title": "The Matrix"}), ("who wrote War and Peace", "book.info", {"title": "War and Peace"}),
    ("capital of Sri Lanka", "country.facts", {"country": "Sri Lanka"}), ("repo psf/requests", "github.repo", {"repo": "psf/requests"}),
    ("github machine learning", "github.search", {"query": "machine learning"}), ("ip 8.8.4.4", "ipinfo.lookup", {"ip": "8.8.4.4"}),
    ("https://Example.com/Path?Q=1", "link.peek", {"url": "https://Example.com/Path?Q=1"}), ("tech of https://example.com", "link.peek", {"section": "tech"}),
    ("2:255 in urdu", "quran.verse", {"ref": "2:255", "lang": "urdu"}), ("surah Al-Baqara", "quran.surah", {"name": "Al-Baqara"}),
    ("tafsir 1:1 jalalayn", "quran.tafsir", {"ref": "1:1", "book": "jalalayn"}), ("news about Artificial Intelligence", "news.about", {"topic": "Artificial Intelligence"}),
    ("google best pizza in lahore", "search.web", {"query": "best pizza in lahore"}), ("good evening", "greetings.daypart", {"part": "evening"}),
]
