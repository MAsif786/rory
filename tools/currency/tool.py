"""Currency conversion with daily ECB rates (Frankfurter, no key)."""
from app.core.schemas import AGAIN, Followup, Input, UserError
from app.core.tool import Tool

tool = Tool("currency", category="everyday", title="Currency", emoji="💱", description="Currency conversion", synonyms={"exchange": "convert"})

NAMES = {"dollar": "USD", "dollars": "USD", "buck": "USD", "bucks": "USD", "euro": "EUR", "euros": "EUR", "pound": "GBP",
         "pounds": "GBP", "sterling": "GBP", "rupee": "PKR", "rupees": "PKR", "rs": "PKR", "riyal": "SAR", "riyals": "SAR",
         "dirham": "AED", "dirhams": "AED", "yen": "JPY", "yuan": "CNY", "rmb": "CNY", "lira": "TRY", "franc": "CHF", "francs": "CHF"}
ISO = ("usd eur gbp pkr inr jpy cny aud cad chf sar aed qar kwd bhd omr egp zar brl mxn rub sgd hkd nzd sek nok dkk myr thb "
       "idr php krw bdt lkr npr").split()          # no 'try'/'all'/'pen': too many ordinary words
_ONE = "(?:" + "|".join([*ISO, *sorted(NAMES, key=len, reverse=True)]) + ")"
CODE = _ONE
CODES = rf"{_ONE}(?:\s*,\s*{_ONE})*"
AMOUNT = r"\d[\d,]*(?:\.\d+)?"

INPUTS = {"amount": Input(type="float", default=1, pattern=AMOUNT), "base": Input(required=True, pattern=CODE),
          "quote": Input(required=True, pattern=CODES)}


def _code(word: str) -> str:
    w = word.strip().lower()
    return NAMES.get(w, w.upper())


@tool.feature(
    "convert", repeat="reuse", description="Convert an amount between currencies",
    phrases=["{amount} {base} to {quote}", "{amount} {base} in {quote}", "convert {amount} {base} to {quote}",
             "convert {amount} {base} {quote}", "convert {amount} {base} into {quote}", "how much is {amount} {base} in {quote}",
             "{base} to {quote}", "{base} in {quote}", "convert {base} to {quote}", "how much is a {base} in {quote}",
             "how much is one {base} in {quote}", "{base} {quote} rate", "{base} to {quote} rate", "rate of {base} in {quote}", "{base}/{quote}"],
    examples=["100 usd to pkr", "convert 50 euros to dollars"],
    negatives=["whether"],
    inputs=INPUTS,
    followups=[Followup(phrases=["and in {quote}", "what about {quote}", "in {quote}"], overrides=["quote"]),
               Followup(phrases=["what about {amount}", "and {amount}"], overrides=["amount"]), AGAIN])
async def convert(ctx, amount, base, quote):
    base, quotes = _code(base), [_code(q) for q in quote.split(",")]
    amount = float(str(amount).replace(",", ""))
    r = await ctx.services.http.get("https://api.frankfurter.dev/v2/rates", params={"base": base, "quotes": ",".join(quotes)})
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise UserError("💱 Unknown currency code. Try USD, EUR, GBP, PKR...")
    lines = [f"💱 *{amount:,.2f} {base}* =", ""]
    lines += [f"• {amount * x['rate']:,.2f} *{x['quote']}* (1 {base} = {x['rate']:.4f})" for x in rows]
    lines.append(f"\n📆 Rates from {rows[0]['date']}")
    return "\n".join(lines)
