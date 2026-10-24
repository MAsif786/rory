"""Help and menu pages, generated from the registry: a new tool shows up here without touching this file.

Format:  <emoji> *Title*  →  blank line  →  body  →  blank line  →  optional "💡" hint.
"""
import random

from app.core.registry import Registry
from app.core.schemas import FeatureSpec
from app.core.tool import Tool

MAX_EXAMPLES = 3


def tip(text: str) -> str:
    return f"💡 {text}"


def _examples(tool: Tool) -> list[str]:
    return [ex for f in tool.features.values() for ex in f.spec.examples][:MAX_EXAMPLES]


def home_menu(registry: Registry) -> str:
    if not registry.tools:
        return "🏠 *Home*\n\nNo tools are installed yet."
    lines = ["🏠 *Home* — what would you like to do?", ""]
    for t in registry.tools.values():
        lines.append(f"{t.emoji} *{t.title}*" + (f" — {t.description}" if t.description else ""))
        if ex := _examples(t):
            lines.append("   _" + " · ".join(ex) + "_")
    lines += ["", tip("*help <tool>* for details · *help all* lists every feature")]
    return "\n".join(lines)


GREETING = [
    "Hey hey! 👋 Good to see you.",
    "Well well, look who showed up! 😎",
    "Yo! 🎉 I've been bored. Let's do something!",
    "Hello, human! 🤖 What can I do for you?",
]


def greeting(registry: Registry) -> str:
    return f"{random.choice(GREETING)}\n\n{home_menu(registry)}"


def not_understood(registry: Registry) -> str:
    """The fallback when nothing matched: show real examples from the installed tools."""
    examples = [t_ex for t in registry.tools.values() for t_ex in _examples(t)[:1]][:4]
    hint = ("Try " + " · ".join(f"_{e}_" for e in examples) + " — or send *menu*") if examples else "Send *menu* to see what I can do"
    return f"🤔 I didn't get that.\n\n{tip(hint)}"


def _feature_lines(spec: FeatureSpec) -> list[str]:
    out = [f"• *{spec.full_name}*" + (f" — {spec.description}" if spec.description else "")]
    if spec.examples:
        out.append("   _" + " · ".join(spec.examples[:MAX_EXAMPLES]) + "_")
    return out


def tool_page(tool: Tool) -> str:
    lines = [f"{tool.emoji} *{tool.title}*" + (f" — {tool.description}" if tool.description else ""), ""]
    for f in tool.features.values():
        lines += _feature_lines(f.spec)
    return "\n".join(lines)


def feature_page(spec: FeatureSpec) -> str:
    lines = [f"*{spec.full_name}*"]
    if spec.description:
        lines.append(spec.description)
    if spec.inputs:
        lines.append("Needs: " + ", ".join(f"{n}{'' if i.required else ' (optional)'}" for n, i in spec.inputs.items()))
    if spec.examples:
        lines.append("Try: _" + " · ".join(spec.examples[:MAX_EXAMPLES]) + "_")
    lines.append(f"_part of the *{spec.tool}* tool_")
    return "\n".join(lines)


def full_help(registry: Registry) -> str:
    if not registry.tools:
        return home_menu(registry)
    return "\n\n".join(tool_page(t) for t in registry.tools.values())


def help_for(registry: Registry, arg: str) -> str:
    """`help`, `help all`, `help weather` (a tool), `help weather.current` or `help forecast` (a feature)."""
    arg = arg.strip().lower().lstrip("!/")
    if not arg:
        return home_menu(registry)
    if arg == "all":
        return full_help(registry)
    if tool := registry.tools.get(arg):
        return tool_page(tool)
    specs = registry.specs()
    hits = [s for s in specs if arg in (s.full_name, s.name)]
    if len(hits) == 1:
        return feature_page(hits[0])
    return f"🤷 No tool or feature called *{arg}*. Send *help all* for the full list."
