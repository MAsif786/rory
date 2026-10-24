"""Group-chat etiquette. In a group Rory answers only when addressed, so it never floods a conversation between people."""
import re
from typing import Literal

Mode = Literal["mention", "all", "off"]


def is_group(chat_id: str) -> bool:
    return chat_id.endswith("@g.us")


def mentioned(payload: dict, me_id: str) -> bool:
    ids = payload.get("mentionedIds") or (payload.get("_data") or {}).get("mentionedJidList") or []
    return bool(me_id) and any(str(i).split("@")[0] == me_id.split("@")[0] for i in ids)


def address(text: str, payload: dict, me_id: str, bot_name: str, mode: Mode, engaged: bool = False) -> str | None:
    """The text Rory should act on, or None to stay silent. Private chats always pass through unchanged.
    In a group (mode "mention") a message is for Rory when it @mentions the bot, starts with its name ("rory, weather in lahore"),
    starts with a command prefix (! or /), or when the group is mid-conversation with it (`engaged`: an active game or open question)."""
    if not is_group(payload.get("from", "")):
        return text
    if mode == "off":
        return None
    if mode == "all":
        return text
    name = re.match(rf"^\s*(?:hey |hi |hello )?@?{re.escape(bot_name)}\b[\s,:;!-]*", text, re.I)
    if name:
        return text[name.end():].strip() or text
    if mentioned(payload, me_id):
        return re.sub(r"@\d{5,}", " ", text).strip() or None        # "@923001234567 weather in lahore" -> "weather in lahore"
    if text.lstrip()[:1] in ("!", "/"):
        return text.lstrip()[1:].strip() or None
    return text if engaged else None
