"""Realistic upstream responses for every network tool, keyed by URL fragment (first match wins, so specific ones come first).
Used by the offline smoke/quality/failure tests: change an API shape here and the tools that depend on it show up as failures."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

PLACE = {"name": "Lahore", "country": "Pakistan", "latitude": 31.5, "longitude": 74.3, "timezone": "Asia/Karachi"}
FORECAST = {"current": {"weather_code": 1, "temperature_2m": 21.4, "apparent_temperature": 20.6, "relative_humidity_2m": 63, "wind_speed_10m": 3.2},
            "daily": {"time": [f"2026-10-{25 + i}" for i in range(5)], "weather_code": [0, 61, 3, 95, 1],
                      "temperature_2m_min": [17] * 5, "temperature_2m_max": [29] * 5, "precipitation_probability_max": [0, 80, 10, None, 5]}}
SURAH = {"number": 2, "englishName": "Al-Baqara", "englishNameTranslation": "The Cow", "name": "سُورَةُ البقرة", "numberOfAyahs": 286,
         "revelationType": "Medinan"}
NAMES = {1: "Al-Faatiha", 2: "Al-Baqara", 36: "Ya-Seen", 55: "Ar-Rahmaan", 112: "Al-Ikhlaas"}
SURAHS = [{**SURAH, "number": i, "englishName": NAMES.get(i, f"Surah {i}"), "numberOfAyahs": 286 if i == 2 else 50} for i in range(1, 115)]
AYAH = {"number": 262, "numberInSurah": 255, "text": "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ", "surah": SURAH,
        "audio": "https://cdn.islamic.network/quran/audio/128/ar.alafasy/262.mp3"}
EDITIONS = [{"edition": {"englishName": "Arabic", "name": "Uthmani"}, "ayahs": [AYAH]},
            {"edition": {"englishName": "Sahih International", "name": "Saheeh"}, "ayahs": [{**AYAH, "text": "Allah - there is no deity except Him"}]}]
AYAH_EDITIONS = [{**AYAH, "edition": {"englishName": "Arabic", "name": "Uthmani"}},
                 {**AYAH, "text": "Allah - there is no deity except Him", "edition": {"englishName": "Sahih International", "name": "Saheeh"}}]
WIKI_PAGE = {"title": "Albert Einstein", "extract": "Albert Einstein was a German-born theoretical physicist best known for the theory of relativity. " * 3,
             "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Albert_Einstein"}}}


def rss() -> str:
    when = format_datetime(datetime.now(timezone.utc) - timedelta(hours=2))
    items = "".join(
        f"<item><title>Story {i} headline - Outlet {i}</title><link>https://news.google.com/rss/articles/CBM{i}</link><pubDate>{when}</pubDate>"
        f"<description>&lt;ol&gt;&lt;li&gt;&lt;a href=\"https://x/{i}\"&gt;Story {i} headline&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color=\"#6f6f6f\"&gt;Outlet {i}&lt;/font&gt;&lt;/li&gt;"
        f"&lt;li&gt;&lt;a href=\"https://y/{i}\"&gt;A different angle on story {i}&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color=\"#6f6f6f\"&gt;Other {i}&lt;/font&gt;&lt;/li&gt;&lt;/ol&gt;</description></item>"
        for i in range(1, 6))
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>News</title>{items}</channel></rss>'


def routes() -> dict:
    return {
        "geocoding-api.open-meteo.com": {"results": [PLACE]},
        "api.open-meteo.com": FORECAST,
        "frankfurter": [{"quote": "PKR", "rate": 280.5, "date": "2026-10-23"}],
        "w/api.php": {"query": {"search": [{"title": "Albert Einstein"}]}},
        "page/summary": WIKI_PAGE,
        "openlibrary.org": {"docs": [{"key": "/works/OL1W", "title": "Dune", "author_name": ["Frank Herbert"], "first_publish_year": 1965,
                                       "number_of_pages_median": 608, "ratings_average": 4.3, "subject": ["Science fiction", "Mars"]}]},
        "apicountries.com": [{"name": "Japan", "flag": "🇯🇵", "capital": "Tokyo", "region": "Asia", "subregion": "Eastern Asia", "population": 125000000,
                              "area": 377930, "languages": [{"name": "Japanese"}], "currencies": [{"name": "Yen", "symbol": "¥"}],
                              "callingCodes": ["81"], "topLevelDomain": [".jp"]}],
        "api.github.com/search": {"items": [{"full_name": "tiangolo/fastapi", "stargazers_count": 90000, "language": "Python", "description": "FastAPI framework"}]},
        "/languages": {"Python": 9000, "Shell": 100},
        "/releases/latest": {"tag_name": "0.100.0", "published_at": "2026-10-01T00:00:00Z"},
        "api.github.com/repos": {"full_name": "tiangolo/fastapi", "description": "FastAPI framework", "stargazers_count": 90000, "forks_count": 7000,
                                 "subscribers_count": 700, "open_issues_count": 400, "license": {"spdx_id": "MIT"}, "size": 12000, "default_branch": "master",
                                 "topics": ["api", "python"], "created_at": "2018-12-08T00:00:00Z", "pushed_at": "2026-10-20T00:00:00Z",
                                 "html_url": "https://github.com/tiangolo/fastapi", "homepage": "https://fastapi.tiangolo.com"},
        "ipinfo.io": {"ip": "8.8.8.8", "city": "Mountain View", "region": "California", "country": "US", "org": "AS15169 Google LLC",
                      "timezone": "America/Los_Angeles", "hostname": "dns.google"},
        "official-joke-api": {"setup": "Why did the scarecrow win an award?", "punchline": "He was outstanding in his field."},
        "uselessfacts": {"text": "Honey never spoils."},
        "editions": lambda url, params: {"data": AYAH_EDITIONS if "/ayah/" in url else EDITIONS},      # two different response shapes
        "/search/": {"data": {"count": 2, "matches": [{"text": "Indeed, Allah is with the patient.", "numberInSurah": 153, "surah": SURAH}]}},
        "alquran.cloud/v1/ayah": {"data": EDITIONS[0]["ayahs"][0] | {"audio": AYAH["audio"]}},
        "alquran.cloud/v1/surah": {"data": SURAHS},
        "news.google.com": rss(),
        "customsearch": {"items": [{"title": "Best Pizza in Lahore", "snippet": "Our top picks for pizza.", "link": "https://pizza.example"}]},
        "opentdb.com": {"results": [{"category": "Science", "question": "What planet is red?", "correct_answer": "Mars",
                                     "incorrect_answers": ["Venus", "Jupiter", "Mercury"]}]},
    }
