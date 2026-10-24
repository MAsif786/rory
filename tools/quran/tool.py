"""Quran: verses, translations, search, surahs, recitation links and tafsir (AlQuran Cloud, no key)."""
import random
import re
from urllib.parse import quote

import httpx

from app.core.schemas import Input, UserError
from app.core.tool import Tool

from . import service as q

tool = Tool("quran", title="Quran", emoji="📖", description="Verses, translations, search, recitation and tafsir")

REF = r"\d{1,3}\s*[:.]\s*\d{1,3}(?:\s*-\s*\d{1,3})?"
LANG = "(?:" + "|".join([*q.LANG_WORDS, *q.LANGS, "ar"]) + ")"
SURAH = r"(?:\d{1,3}|[a-zA-Z' -]{2,30})"
TAFSIR = "(?:" + "|".join(q.TAFSIRS) + ")"
LANG_IN = Input(default="en", pattern=LANG)


@tool.feature(
    "verse", repeat="reuse", description="A verse or range, optionally in another language (2:255, 2:255-257, 2:255 in urdu)",
    phrases=["{ref}", "quran {ref}", "read quran {ref}", "read {ref}", "ayah {ref}", "ayat {ref}", "verse {ref}", "surah {ref}", "{ref} in {lang}", "quran {ref} in {lang}",
             "quran {ref} {lang}", "{ref} {lang}", "ayah {ref} in {lang}", "verse {ref} in {lang}"],
    examples=["2:255", "quran 112:1-4 in urdu"],
    inputs={"ref": Input(required=True, pattern=REF), "lang": LANG_IN})
async def verse(ctx, ref, lang):
    s_no, start, end = q.parse_ref(ref)
    return await q.fetch_range(ctx.services.http, s_no, start, end, q.lang_code(lang))


@tool.feature(
    "kursi", repeat="reuse", description="Ayat al-Kursi (2:255), optionally in another language",
    phrases=["ayat al kursi", "ayat ul kursi", "ayatul kursi", "ayat e kursi", "ayat al-kursi", "ayah al kursi", "throne verse",
             "ayat al kursi in {lang}", "ayatul kursi in {lang}", "ayat ul kursi in {lang}"],
    examples=["ayat al kursi in urdu", "ayatul kursi"],
    inputs={"lang": LANG_IN})
async def kursi(ctx, lang):
    return await q.fetch_range(ctx.services.http, 2, 255, 255, q.lang_code(lang))


@tool.feature(
    "random", description="A random verse",
    phrases=["random verse", "random ayah", "random ayat", "quran random", "random quran verse", "a random verse", "random verse in {lang}",
             "quran random in {lang}", "give me a verse", "verse of the day", "ayah of the day"],
    examples=["random verse", "verse of the day"],
    inputs={"lang": LANG_IN})
async def random_verse(ctx, lang):
    lang = q.lang_code(lang)
    editions = q.ARABIC if lang == "ar" else f"{q.ARABIC},{q.LANGS[lang]}"
    data = await q.get(ctx.services.http, f"/ayah/{random.randint(1, 6236)}/editions/{editions}")
    a = data[0]
    return q.format_ayahs(a["surah"], [a], [data[1]] if lang != "ar" else None, data[1]["edition"]["englishName"] if lang != "ar" else "")


@tool.feature(
    "search", repeat="reuse", description="Search the translation for a word or topic (verses about patience)",
    phrases=["quran search {kw}", "search quran for {kw}", "search the quran for {kw}", "verses about {kw}", "verses on {kw}",
             "ayat about {kw}", "ayahs about {kw}", "find verses about {kw}", "quran verses about {kw}", "what does the quran say about {kw}"],
    examples=["verses about patience", "search quran for mercy"],
    inputs={"kw": Input(required=True, pattern=r"[^\n]{3,60}", ask="🔎 What should I search the Quran for?")})
async def search(ctx, kw):
    arabic_query = bool(re.search(r"[؀-ۿ]", kw))
    try:
        data = await q.get(ctx.services.http, f"/search/{quote(kw, safe='')}/all/{'quran-simple' if arabic_query else q.LANGS['en']}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise UserError(f"🔎 No verses found for *{kw}*.") from None
        raise
    matches = data["matches"]
    lines = [f"🔎 *{data['count']} verses* match “{kw}” — top {min(5, len(matches))}:", ""]
    for m in matches[:5]:
        txt = " ".join(m["text"].split())
        txt = txt if len(txt) <= 170 else txt[:167].rsplit(" ", 1)[0] + "…"
        lines.append(f"• *{m['surah']['number']}:{m['numberInSurah']}* ({m['surah']['englishName']})\n  {txt}")
    lines.append("\nOpen one by sending its number, e.g. *2:218*")
    return "\n".join(lines)


@tool.feature(
    "surah", repeat="reuse", description="A surah by name or number (first 5 verses)",
    phrases=["surah {name}", "sura {name}", "quran surah {name}", "read surah {name}", "surah {name} in {lang}", "tell me about surah {name}",
             "show me surah {name}", "surat {name}"],
    examples=["surah rahman", "read surah 36"],
    inputs={"name": Input(required=True, pattern=SURAH, ask="📖 Which surah? e.g. *Rahman* or *55*"), "lang": LANG_IN})
async def surah(ctx, name, lang):
    http = ctx.services.http
    s = await q.find_surah(http, name)
    text = await q.fetch_range(http, s["number"], 1, q.PREVIEW, q.lang_code(lang))
    info = f"\n\n{s['revelationType']} · {s['numberOfAyahs']} verses"
    if s["numberOfAyahs"] > q.PREVIEW:
        info += f"\nNext: send *{s['number']}:{q.PREVIEW + 1}-{min(q.PREVIEW + q.MAX_RANGE, s['numberOfAyahs'])}*"
    return text + info


@tool.feature(
    "audio", repeat="reuse", description="Recitation of a verse (Mishary Alafasy) as an audio link",
    phrases=["audio {ref}", "quran audio {ref}", "recite {ref}", "listen to {ref}", "recitation of {ref}", "play ayah {ref}", "audio of {ref}"],
    examples=["audio 1:1", "recite 2:255"],
    inputs={"ref": Input(required=True, pattern=REF)})
async def audio(ctx, ref):
    http = ctx.services.http
    s_no, a_no, _ = q.parse_ref(ref)
    s = await q.check_verse(http, s_no, a_no)
    data = await q.get(http, f"/ayah/{s_no}:{a_no}/{q.RECITER}")
    return f"🎧 {s['englishName']} {s_no}:{a_no} — Mishary Alafasy\n{data['audio']}"


@tool.feature(
    "surah_audio", repeat="reuse", description="Full-surah recitation link",
    phrases=["audio surah {name}", "quran audio surah {name}", "recite surah {name}", "listen to surah {name}", "play surah {name}",
             "full recitation of surah {name}"],
    examples=["audio surah rahman", "recite surah yasin"],
    inputs={"name": Input(required=True, pattern=SURAH)})
async def surah_audio(ctx, name):
    s = await q.find_surah(ctx.services.http, name)
    return (f"🎧 *{s['englishName']}* full recitation (Mishary Alafasy):\n"
            f"https://cdn.islamic.network/quran/audio-surah/128/{q.RECITER}/{s['number']}.mp3")


@tool.feature(
    "tafsir", repeat="reuse", description="Arabic tafsir of a verse (muyassar; also jalalayn, qurtubi, waseet, baghawi)",
    keywords=["tafsir", "tafseer"],
    phrases=["tafsir {ref}", "tafseer {ref}", "quran tafsir {ref}", "tafsir of {ref}", "tafsir {ref} {book}", "tafsir of {ref} by {book}",
             "explain verse {ref}"],
    examples=["tafsir 2:255", "tafsir 1:1 jalalayn"],
    inputs={"ref": Input(required=True, pattern=REF), "book": Input(default="muyassar", pattern=TAFSIR)})
async def tafsir(ctx, ref, book):
    http = ctx.services.http
    s_no, a_no, _ = q.parse_ref(ref)
    s = await q.check_verse(http, s_no, a_no)
    data = await q.get(http, f"/ayah/{s_no}:{a_no}/editions/{q.ARABIC},{q.TAFSIRS[book.lower()]}")
    txt = " ".join(data[1]["text"].split())
    if len(txt) > 1800:
        txt = txt[:1800].rsplit(" ", 1)[0] + "…"
    return (f"📚 *Tafsir — {s['englishName']} {s_no}:{a_no}*\n\n{q.clean_arabic(data[0]['text'], s_no, a_no)}\n\n"
            f"{txt}\n\n— {data[1]['edition']['name']} (Arabic)")
