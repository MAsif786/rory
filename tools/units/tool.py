"""Unit conversion: length, mass, volume and temperature."""
from app.core.schemas import Input, UserError
from app.core.tool import Tool

tool = Tool("units", category="everyday", title="Units", emoji="📏", description="Unit conversion")

ALIASES = {"meter": "m", "meters": "m", "metre": "m", "metres": "m", "kilometer": "km", "kilometers": "km", "kilometre": "km",
           "kilometres": "km", "centimeter": "cm", "centimeters": "cm", "millimeter": "mm", "mile": "mi", "miles": "mi",
           "foot": "ft", "feet": "ft", "inch": "in", "inches": "in", "yard": "yd", "yards": "yd", "kilogram": "kg",
           "kilograms": "kg", "kgs": "kg", "gram": "g", "grams": "g", "pound": "lb", "pounds": "lb", "lbs": "lb",
           "ounce": "oz", "ounces": "oz", "liter": "l", "liters": "l", "litre": "l", "litres": "l", "milliliter": "ml",
           "gallon": "gal", "gallons": "gal", "celsius": "c", "fahrenheit": "f", "kelvin": "k", "°c": "c", "°f": "f"}
LINEAR = {"m": ("len", 1), "km": ("len", 1000), "cm": ("len", 0.01), "mm": ("len", 0.001), "mi": ("len", 1609.344),
          "ft": ("len", 0.3048), "in": ("len", 0.0254), "yd": ("len", 0.9144),
          "kg": ("mass", 1), "g": ("mass", 0.001), "lb": ("mass", 0.45359237), "oz": ("mass", 0.0283495),
          "l": ("vol", 1), "ml": ("vol", 0.001), "gal": ("vol", 3.78541)}
TEMPS = {"c", "f", "k"}
_UNIT = "(?:" + "|".join(sorted({*ALIASES, *LINEAR, *TEMPS}, key=len, reverse=True)) + ")"
NUMBER = r"-?\d+(?:\.\d+)?"


def convert_units(value: float, a: str, b: str) -> str | None:
    a, b = ALIASES.get(a, a), ALIASES.get(b, b)
    if a in TEMPS and b in TEMPS:
        x = value if a == "c" else (value - 32) * 5 / 9 if a == "f" else value - 273.15
        out = x if b == "c" else x * 9 / 5 + 32 if b == "f" else x + 273.15
        return f"🌡️ {value:g}°{a.upper()} = *{out:.2f}°{b.upper()}*"
    if a in LINEAR and b in LINEAR and LINEAR[a][0] == LINEAR[b][0]:
        return f"📏 {value:g} {a} = *{value * LINEAR[a][1] / LINEAR[b][1]:,.4g} {b}*"
    return None


@tool.feature(
    "convert", description="Convert between units",
    phrases=["{value} {src} to {dst}", "{value} {src} in {dst}", "convert {value} {src} to {dst}", "how many {dst} in {value} {src}",
             "{value}{src} to {dst}", "{value}{src} in {dst}", "what's {value} {src} in {dst}", "what is {value} {src} in {dst}",
             "how many {dst} are in {value} {src}", "how many {dst} is {value} {src}", "how many {dst} in a {src}"],
    examples=["5 km in miles", "convert 20 celsius to fahrenheit"],
    inputs={"value": Input(type="float", required=True, pattern=NUMBER), "src": Input(required=True, pattern=_UNIT),
            "dst": Input(required=True, pattern=_UNIT)})
async def convert(ctx, value, src, dst):
    out = convert_units(value, src.lower(), dst.lower())
    if out is None:
        raise UserError(f"📏 I can't convert {src} to {dst} (they measure different things).")
    return out
