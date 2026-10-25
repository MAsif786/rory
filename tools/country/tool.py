"""Country facts."""
from urllib.parse import quote

import httpx

from app.core.schemas import Followup, Input, UserError
from app.core.tool import Tool

tool = Tool("country", title="Countries", emoji="🌍", description="Facts about any country", synonyms={"nation": "country"})

# a country is one to four words and never starts like a list or a request ("list of jokes or" is not a country)
NAME = r"(?!(?:list|any|some|all|my|your|more|best|top)\b)[A-Za-z'.-]+(?: (?:of |the |and |d')?[A-Za-z'.-]+){0,3}"


@tool.feature(
    "facts", repeat="reuse", description="Capital, population, languages and currency of a country",
    phrases=["country {country}", "the country {country}", "capital of {country}", "what is the capital of {country}",
             "what's the capital of {country}", "population of {country}", "what is the population of {country}",
             "facts about {country}", "tell me about the country {country}", "{country} country facts", "{country} facts"],
    examples=["capital of France", "country Japan"],
    inputs={"country": Input(required=True, pattern=NAME, ask="🌍 Which country?")},
    followups=[Followup(phrases=["what about {country}", "how about {country}", "and {country}"], overrides=["country"])])
async def facts(ctx, country):
    try:
        r = await ctx.services.http.get(f"https://www.apicountries.com/name/{quote(country, safe='')}")
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise UserError(f"🌍 No country found for *{country}*.") from None
        raise
    data = r.json()
    if not data:
        raise UserError(f"🌍 No country found for *{country}*.")
    c = next((x for x in data if x["name"].lower() == country.lower()), data[0])
    langs = ", ".join(l["name"] for l in c.get("languages", [])[:4])
    cur = ", ".join(f"{x['name']} ({x.get('symbol', '')})" for x in c.get("currencies", [])[:2])
    return (f"{c.get('flag', '🌍')} *{c['name']}*\n"
            f"🏛️ Capital: {c.get('capital', '—')}\n"
            f"🌐 {c.get('region', '')}{' · ' + c['subregion'] if c.get('subregion') else ''}\n"
            f"👥 Population: {c.get('population', 0):,}\n"
            f"📐 Area: {c.get('area', 0):,.0f} km²\n"
            f"🗣️ {langs}\n💰 {cur}\n📞 +{(c.get('callingCodes') or ['?'])[0]} · {(c.get('topLevelDomain') or ['?'])[0]}")
