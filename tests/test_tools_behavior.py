"""Behaviour of the ported tools, end to end through the bot, with a fake HTTP client (no network)."""
import random
from types import SimpleNamespace

import httpx

import pytest

from app.core.context import ContextStore
from app.core.dispatcher import Dispatcher
from app.core.registry import Registry
from app.intent.rule_based import decide
from app.smart import Bot

REGISTRY = Registry().discover()


class FakeHttp:
    """Maps a URL fragment to a JSON body; anything else raises like a dead network."""
    def __init__(self, routes=None):
        self.routes, self.calls = routes or {}, []

    async def get(self, url, params=None, headers=None):
        self.calls.append((url, params))
        for fragment, body in self.routes.items():
            if fragment in url:
                text = body if isinstance(body, str) else ""
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda b=body: b, text=text)
        raise httpx.ConnectError(f"no route for {url}")


def make_bot(routes=None):
    http = FakeHttp(routes)
    return Bot(REGISTRY, Dispatcher(REGISTRY), decide, ContextStore(), SimpleNamespace(http=http)), http


@pytest.fixture
def bot():
    return make_bot()[0]


async def say(bot, text, chat="c"):
    return await bot.handle(chat, text)


# --- pure tools ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("25*8", "*200*"), ("what is 12 + 30", "*42*"), ("sqrt(144)", "*12*"), ("2^10", "*1024*"), ("calc 10/4", "*2.5*"),
    ("15% of 200", "*30*"), ("what is 20 percent of 50", "*10*"), ("5 / 0", "Division by zero"), ("9**9**9", "too big")])
async def test_calc(bot, text, expected):
    assert expected in await say(bot, text)


async def test_calc_asks_when_expression_missing(bot):
    assert "What should I calculate" in await say(bot, "calculate")
    assert "*8*" in await say(bot, "2*4")


@pytest.mark.parametrize("text, expected", [
    ("5 km in miles", "3.107 mi"), ("convert 20 celsius to fahrenheit", "68.00°F"), ("2 kg to lb", "4.409 lb"),
    ("5 km to kg", "can't convert")])
async def test_units(bot, text, expected):
    assert expected in await say(bot, text)


async def test_dice_flip_roll_choose(bot):
    random.seed(1)
    assert await say(bot, "flip a coin") in ("🪙 *Heads!*", "🪙 *Tails!*")
    assert "2d6" in await say(bot, "roll 2d6") and "1d6" in await say(bot, "roll a dice")
    assert "between 1 and 20" in (await say(bot, "roll 99d6")).lower()
    assert "I pick: *" in await say(bot, "choose between pizza, sushi or tacos")


async def test_clock_utc_needs_no_network(bot):
    out = await say(bot, "what time is it")
    assert "*UTC*" in out and "⏰" in out
    assert "Asia/Karachi" in await say(bot, "time in Asia/Karachi")


# --- network tools (fake responses) ------------------------------------------------------------------------------
async def test_currency_converts_and_follows_up():
    bot, http = make_bot({"frankfurter": [{"quote": "PKR", "rate": 280.5, "date": "2026-10-23"}]})
    out = await say(bot, "100 usd to pkr")
    assert "28,050.00 *PKR*" in out and http.calls[0][1] == {"base": "USD", "quotes": "PKR"}
    await say(bot, "convert 50 euros to dollars")
    assert http.calls[-1][1] == {"base": "EUR", "quotes": "USD"}
    await say(bot, "what about 10")
    assert "amount" not in str(http.calls[-1])                                  # follow-up re-ran with new amount
    assert http.calls[-1][1] == {"base": "EUR", "quotes": "USD"}


async def test_currency_unknown_code_is_friendly():
    bot, _ = make_bot({"frankfurter": []})
    assert "Unknown currency" in await say(bot, "100 usd to pkr")


async def test_wiki_and_followup():
    bot, http = make_bot({"w/api.php": {"query": {"search": [{"title": "Albert Einstein"}]}},
                          "page/summary": {"title": "Albert Einstein", "extract": "German-born physicist. " * 5,
                                           "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Albert_Einstein"}}}})
    out = await say(bot, "who is Einstein")
    assert out.startswith("📚 *Albert Einstein*") and "wikipedia.org/wiki/Albert_Einstein" in out
    await say(bot, "what about Newton")
    assert http.calls[-2][1]["srsearch"] == "Newton"


async def test_country_not_found_is_friendly():
    bot, http = make_bot()

    async def get(url, params=None, headers=None):
        raise httpx.HTTPStatusError("nope", request=httpx.Request("GET", url), response=httpx.Response(404))
    http.get = get
    assert "No country found for *atlantis*" in await say(bot, "capital of atlantis")


async def test_quran_verse_and_ayat_kursi():
    surahs = [{"number": 2, "englishName": "Al-Baqara", "englishNameTranslation": "The Cow", "name": "سُورَةُ البقرة",
               "numberOfAyahs": 286, "revelationType": "Medinan"}]
    surahs = [{**surahs[0], "number": i} if i == 2 else {**surahs[0], "number": i, "englishName": f"S{i}"} for i in range(1, 115)]
    editions = [{"edition": {"englishName": "Arabic"}, "ayahs": [{"numberInSurah": 255, "text": "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ"}]},
                {"edition": {"englishName": "Sahih International"}, "ayahs": [{"numberInSurah": 255, "text": "Allah - there is no deity"}]}]
    bot, http = make_bot({"/surah/2/editions": {"data": editions}, "/surah": {"data": surahs}})
    for text in ("2:255", "ayat al kursi", "quran 2:255 in english"):
        out = await say(bot, text)
        assert "*2:255*" in out and "no deity" in out and "Sahih International" in out
    assert "114 surahs" in await say(bot, "200:1")


async def test_github_repo_requires_owner_slash_name(bot):
    assert "Which repo" in await say(bot, "repo")


async def test_ipinfo_rejects_private_addresses(bot):
    assert "private" in await say(bot, "192.168.1.1")


async def test_link_without_url_asks(bot):
    assert "Which link" in await say(bot, "link")


# --- games ---------------------------------------------------------------------------------------------------------
GAMES = ["blackjack", "dungeon", "guess", "hangman", "highlow", "memory", "quiz", "rps", "trivia", "ttt"]


@pytest.mark.parametrize("game", GAMES)
async def test_every_game_starts_and_quits(game):
    bot, _ = make_bot()                             # fake http raises -> trivia/quiz fall back to the offline bank
    intro = await say(bot, f"play {game}")
    assert intro and bot.store.get("c").session and bot.store.get("c").session.tool == game
    assert await say(bot, "quit") == "Game ended." and bot.store.get("c").session is None


async def test_guess_game_plays_to_a_win(bot):
    await say(bot, "play guess")
    game = bot.store.get("c").session.state
    game.secret = 42
    assert "higher" in await say(bot, "10")
    assert "42" in await say(bot, "42")
    assert bot.store.get("c").session is None                                   # finished -> session cleared


async def test_game_ignores_unrelated_chat_via_passthrough():
    bot, _ = make_bot()
    await say(bot, "play trivia")
    assert "Home" in await say(bot, "menu")                                     # menu works mid-game
    assert bot.store.get("c").session is not None
    assert "Rory" in await say(bot, "hello")                                    # unrelated chat falls through to the greeting
    assert bot.store.get("c").session is not None


async def test_game_aliases_start_games(bot):
    assert "Rock Paper Scissors" in await say(bot, "play rock paper scissors")
    await say(bot, "stop")
    assert "Tic" in await say(bot, "lets play tic tac toe")


def test_find_url_keeps_closing_bracket_of_wikipedia_titles():
    from tools.link.linkpeek import find_url
    assert find_url("https://en.wikipedia.org/wiki/Python_(programming_language)") == "https://en.wikipedia.org/wiki/Python_(programming_language)"
    assert find_url("see (https://example.com/a).") == "https://example.com/a"


# --- news & web search ------------------------------------------------------------------------------------------------
RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Rover finds ice on Mars - Space Daily</title><link>https://news.example/1</link><pubDate>{when}</pubDate></item>
<item><title>Second story - Other Source</title><link>https://news.example/2</link><pubDate>{when}</pubDate></item></channel></rss>"""


def rss_bot():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime
    body = RSS.format(when=format_datetime(datetime.now(timezone.utc) - timedelta(hours=3)))
    return make_bot({"news.google.com": body})


async def test_news_headlines_and_topic():
    bot, http = rss_bot()
    out = await say(bot, "today's news")
    assert "📰 *Top headlines*" in out and "1. *Rover finds ice on Mars*" in out and "Space Daily · 3h ago" in out
    assert "q" not in http.calls[0][1]                                          # the top-stories feed
    out = await say(bot, "news about mars")
    assert "📰 *News: mars*" in out and http.calls[-1][1]["q"] == "mars when:2d"
    await say(bot, "pakistan news")
    assert http.calls[-1][1]["q"] == "pakistan when:2d"
    await say(bot, "what about cricket")                                         # follow-up keeps the news feature
    assert http.calls[-1][1]["q"] == "cricket when:2d"


async def test_news_bad_feed_is_friendly():
    bot, _ = make_bot({"news.google.com": "<not xml"})
    assert "couldn't read the news feed" in await say(bot, "latest news")


async def test_news_is_not_triggered_by_small_talk(bot):
    for text in ("good news", "that is bad news", "no news"):
        assert "📰" not in (await say(bot, text) or "")


async def test_web_search_needs_a_key_then_returns_results(monkeypatch):
    bot, http = make_bot({"customsearch": {"items": [{"title": "Best Pizza", "snippet": "Top pizza places", "link": "https://pizza.example"}]}})
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert "isn't set up yet" in await say(bot, "google best pizza")
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_CSE_ID", "cx")
    out = await say(bot, "search for pizza in lahore")
    assert "1. *Best Pizza*" in out and "https://pizza.example" in out
    assert http.calls[-1][1]["q"] == "pizza in lahore" and http.calls[-1][1]["num"] == 5
