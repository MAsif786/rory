"""Rory's web chat: a page at /chat plus a tiny JSON API over the same Bot that WhatsApp uses.

Each browser gets an anonymous cookie; its chat id is "web:<token>", so follow-ups and games work exactly like a WhatsApp DM.
"""
import html
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app import trace
from app.settings import get_settings

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=BASE / "templates")
router = APIRouter()
settings = get_settings()

COOKIE = "rory_web"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30
SUGGESTIONS = ["tell me a joke", "fun fact", "weather in lahore", "100 usd to pkr", "today's news", "play tic-tac-toe"]      # most-loved first: jokes and facts
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_URL = re.compile(r"https?://[^\s<]+")


def render(text: str) -> str:
    """WhatsApp-style text -> safe HTML. Everything is escaped first; only *bold*, _italic_, ~strike~ and http(s) links are added back."""
    out = html.escape(text, quote=True)
    out = _URL.sub(lambda m: _link(m.group(0)), out)
    out = re.sub(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])", r"<em>\1</em>", out)
    out = re.sub(r"(?<![\w~])~(?=\S)([^~\n]+?)(?<=\S)~(?![\w~])", r"<s>\1</s>", out)
    return out


def _link(escaped: str) -> str:
    url = escaped.rstrip(".,;:!?)")                       # trailing punctuation belongs to the sentence, not the link
    rest = escaped[len(url):]
    return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>{rest}'


def examples() -> list[dict]:
    """Everything Rory's tools say people can type, for the typeahead (hidden tools such as greetings are left out).
    "amount" marks examples of features that take a number (100 usd to pkr, 5 km in miles): the page swaps in the number the visitor typed."""
    from app import main
    seen: dict[str, bool] = {}
    for spec in main.registry.specs():
        if spec.tool == "greetings":
            continue
        takes_number = any(i.type in ("int", "float") for i in spec.inputs.values())
        for e in spec.examples:
            if "{" not in e:
                seen.setdefault(e, takes_number)
    return [{"text": text, "amount": amount} for text, amount in seen.items()]


def suggestions_after(chat_id: str) -> list[str]:
    """One-tap next steps, built only from what Rory really accepts: leave a running game, repeat a repeatable answer, or ask for help."""
    from app import main
    t = trace.current()
    if t.get("kind") in ("fallback", "out_of_scope"):
        return ["help"]
    ctx = main.bot.store.peek(chat_id)
    if ctx and ctx.session:
        return ["quit"]
    spec = main.registry.spec(ctx.last_turn.feature) if ctx and ctx.last_turn and t.get("kind") == "answer" else None
    if spec:
        phrases = [p for f in spec.followups for p in f.phrases if "{" not in p]
        return [p for p in ("again", "one more", "another") if p in phrases][:1]
    return []


def label_for() -> str | None:
    """The visible name of the tool that produced this reply ("Weather", "Tic-Tac-Toe"), so people can see where an answer came from."""
    from app import main
    tool = main.registry.tools.get(str(trace.current().get("feature", "")).partition(".")[0])
    return tool.title if tool and not tool.hidden else None


def _chat_id(request: Request) -> str | None:
    token = request.cookies.get(COOKIE, "")
    return f"web:{token}" if _TOKEN.match(token) else None


def _set_cookie(request: Request, response, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", secure=request.url.scheme == "https", path="/")


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    return not origin or urlsplit(origin).netloc == request.headers.get("host", "")


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


@router.get("/chat", response_class=HTMLResponse)
async def page(request: Request):
    response = templates.TemplateResponse(request, "chat.html", {"bot_name": settings.bot_name.capitalize(), "suggestions": SUGGESTIONS, "examples": examples(),
                                                                   "max_chars": settings.max_message_chars})
    if not _chat_id(request):
        _set_cookie(request, response, secrets.token_urlsafe(18))
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/chat/message")
async def message(request: Request):
    from app import main                                  # late: main includes this router, and tests rebuild main's state
    if not _same_origin(request):
        return _error("Blocked: this request came from another site.", 403)
    chat_id = _chat_id(request)
    if not chat_id:
        return _error("Your session expired. Reload the page to start again.", 400)
    try:
        body = await request.json()
    except ValueError:
        body = None
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip():
        return _error("Type a message first.", 400)
    text = text.strip()
    if len(text) > settings.max_message_chars:
        return _error(main.TOO_LONG.format(n=settings.max_message_chars), 413)
    trace.start()
    async with main.locks(chat_id):
        if main.limiter.check(chat_id) != "ok":
            return _error(main.RATE_NOTICE, 429)
        reply = await main.reply_for(chat_id, text)
        suggest, label = suggestions_after(chat_id), label_for()
    return {"ok": True, "text": reply, "html": render(reply), "suggestions": suggest, "label": label}


@router.post("/chat/reset")
async def reset(request: Request):
    from app import main
    if not _same_origin(request):
        return _error("Blocked: this request came from another site.", 403)
    if chat_id := _chat_id(request):
        main.bot.store._chats.pop(chat_id, None)
    response = JSONResponse({"ok": True})
    _set_cookie(request, response, secrets.token_urlsafe(18))
    return response
