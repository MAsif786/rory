"""AlQuran Cloud API access and formatting (no key needed)."""
import re
from difflib import get_close_matches

from app.core.schemas import UserError

API = "https://api.alquran.cloud/v1"
ARABIC = "quran-uthmani"
RECITER = "ar.alafasy"
MAX_RANGE = 7        # ayahs per reply
PREVIEW = 5          # ayahs shown for a surah
LANGS = {"en": "en.sahih", "ur": "ur.jalandhry", "hi": "hi.hindi", "bn": "bn.bengali", "id": "id.indonesian", "tr": "tr.diyanet",
         "fr": "fr.hamidullah", "es": "es.cortes", "de": "de.aburida", "ru": "ru.kuliev", "fa": "fa.makarem"}
LANG_WORDS = {"english": "en", "urdu": "ur", "arabic": "ar", "hindi": "hi", "bengali": "bn", "indonesian": "id", "turkish": "tr",
              "french": "fr", "spanish": "es", "german": "de", "russian": "ru", "persian": "fa"}
TAFSIRS = {"muyassar": "ar.muyassar", "jalalayn": "ar.jalalayn", "qurtubi": "ar.qurtubi", "waseet": "ar.waseet", "baghawi": "ar.baghawi"}
_surahs: list[dict] = []


async def get(http, path: str, **params):
    r = await http.get(f"{API}{path}", params=params or None)
    r.raise_for_status()
    return r.json()["data"]


async def surahs(http) -> list[dict]:
    if not _surahs:
        _surahs.extend(await get(http, "/surah"))
    return _surahs


def _norm(s: str) -> str:
    s = re.sub(r"[^a-z]", "", s.lower())
    return re.sub(r"(.)\1+", r"\1", s)       # collapse doubled letters: Rahmaan -> rahman


async def find_surah(http, q: str) -> dict:
    q, lst = q.strip(), await surahs(http)
    if q.isdigit():
        if 1 <= int(q) <= len(lst):
            return lst[int(q) - 1]
        raise UserError("There are 114 surahs (1–114).")
    nq = _norm(q)
    if not nq:
        raise UserError("📖 Which surah? e.g. *surah Rahman* or *55*")
    names = {s["number"]: _norm(s["englishName"]) for s in lst}
    for n, nn in names.items():
        if nn == nq:
            return lst[n - 1]
    for n, nn in names.items():
        if nq in nn or nn in nq and len(nn) > 3:
            return lst[n - 1]
    for s in lst:
        if nq in _norm(s["englishNameTranslation"]):
            return s
    if close := get_close_matches(nq, list(names.values()), n=1, cutoff=0.6):
        return lst[next(n for n, nn in names.items() if nn == close[0]) - 1]
    raise UserError(f"📖 I couldn't find a surah called *{q}*.")


def lang_code(token: str | None) -> str:
    code = LANG_WORDS.get((token or "en").lower(), (token or "en").lower())
    if code != "ar" and code not in LANGS:
        raise UserError(f"🌐 Unknown language *{token}*. Available: ar, {', '.join(LANGS)}")
    return code


def clean_arabic(text: str, surah: int, ayah: int) -> str:
    """The API prepends the basmala to ayah 1 of most surahs; drop it (it's not part of the verse)."""
    text = text.replace("﻿", "").strip()
    if ayah == 1 and surah not in (1, 9):
        words = text.split()
        if len(words) > 4 and words[0].startswith("بِسْمِ"):
            return " ".join(words[4:])
    return text


def format_ayahs(s: dict, arabic: list[dict], trans: list[dict] | None, edition_name: str) -> str:
    out = [f"📖 *{s['englishName']}* ({s['englishNameTranslation']}) — {s['name'].replace('سُورَةُ', '').strip()}"]
    for i, a in enumerate(arabic):
        n = a["numberInSurah"]
        block = [f"\n*{s['number']}:{n}*", clean_arabic(a["text"], s["number"], n)]
        if trans:
            block.append(f"_{trans[i]['text']}_")
        out.append("\n".join(block))
    if trans:
        out.append(f"\n— {edition_name}")
    return "\n".join(out)


async def fetch_range(http, surah_no: int, start: int, end: int, lang: str) -> str:
    lst = await surahs(http)
    if not 1 <= surah_no <= 114:
        raise UserError("There are 114 surahs (1–114).")
    s = lst[surah_no - 1]
    if not 1 <= start <= s["numberOfAyahs"] or end < start:
        raise UserError(f"{s['englishName']} has {s['numberOfAyahs']} verses.")
    end = min(end, s["numberOfAyahs"], start + MAX_RANGE - 1)
    editions = ARABIC if lang == "ar" else f"{ARABIC},{LANGS[lang]}"
    data = await get(http, f"/surah/{surah_no}/editions/{editions}", offset=start - 1, limit=end - start + 1)
    arabic, trans = data[0]["ayahs"], (data[1]["ayahs"] if lang != "ar" else None)
    return format_ayahs(s, arabic, trans, data[1]["edition"]["englishName"] if trans else "")


_REF = re.compile(r"^(\d{1,3})\s*[:.]\s*(\d{1,3})(?:\s*-\s*(\d{1,3}))?$")


def parse_ref(text: str) -> tuple[int, int, int]:
    m = _REF.match(text.strip())
    if not m:
        raise UserError("📖 Use a verse reference like *2:255* or *2:255-257*.")
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or m.group(2))


async def check_verse(http, s_no: int, a_no: int) -> dict:
    if not 1 <= s_no <= 114:
        raise UserError("There are 114 surahs (1–114).")
    s = (await surahs(http))[s_no - 1]
    if not 1 <= a_no <= s["numberOfAyahs"]:
        raise UserError(f"{s['englishName']} has {s['numberOfAyahs']} verses.")
    return s
