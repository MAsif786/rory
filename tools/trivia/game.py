import asyncio
import html
import random

import httpx

from app.fun import pick
from app.games import Game
from .bank import BANK

QUESTION_TIMEOUT = 3          # seconds: a slow trivia API must not keep a player waiting; the offline bank is the fallback
LETTERS = "ABCD"
RIGHT = ["✅ Correct!", "🎯 Nailed it!", "🧠 Big brain!"]
WRONG = ["❌ Nope!", "🙈 Not quite!", "😬 Ouch, no."]


async def fetch_question(http) -> dict:
    """OpenTDB first, offline bank as fallback. `http` is the shared httpx client (ctx.services.http)."""
    try:
        r = await asyncio.wait_for(http.get("https://opentdb.com/api.php", params={"amount": 1, "type": "multiple"}), QUESTION_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        q = data["results"][0]
        return {
            "cat": html.unescape(q["category"]),
            "q": html.unescape(q["question"]),
            "correct": html.unescape(q["correct_answer"]),
            "wrong": [html.unescape(a) for a in q["incorrect_answers"]],
        }
    except (httpx.HTTPError, asyncio.TimeoutError, KeyError, IndexError, ValueError):
        cat, q, c, w = random.choice(BANK)
        return {"cat": cat, "q": q, "correct": c, "wrong": list(w)}


class Trivia(Game):
    key = "trivia"
    title = "Trivia"
    order = 70
    aliases = ("trivia", "trivia game", "trivia question", "a trivia question")
    description = "One quick question"
    group_ok = True
    rounds = 1
    points = 10

    def __init__(self) -> None:
        self.round = 0
        self.q: dict | None = None
        self.choices: list[str] = []
        self.locked: set[str] = set()   # players who already missed this question
        self.scores: dict[str, int] = {}
        self._done = False

    async def _next(self) -> str:
        self.round += 1
        self.q = await fetch_question(self.ctx.services.http)
        self.choices = self.q["wrong"] + [self.q["correct"]]
        random.shuffle(self.choices)
        self.locked.clear()
        opts = "\n".join(f"{LETTERS[i]}) {c}" for i, c in enumerate(self.choices))
        head = f"🧠 *Trivia* — {self.q['cat']}" + (f" (Q{self.round}/{self.rounds})" if self.rounds > 1 else "")
        return f"{head}\n\n{self.q['q']}\n\n{opts}\n\nReply *A*, *B*, *C* or *D*. (*quit* to stop)"

    async def start(self) -> str:
        return await self._next()

    def _parse(self, text: str) -> int | None:
        t = text.strip().lower().rstrip(").")
        if t and len(t) == 1 and t in "abcd":
            return "abcd".index(t)
        if t in ("1", "2", "3", "4"):
            return int(t) - 1
        for i, c in enumerate(self.choices):
            if t == c.lower():
                return i
        return None

    async def _advance(self, prefix: str) -> str:
        if self.round >= self.rounds:
            self._done = True
            board = ""
            if self.rounds > 1 and self.scores:
                ranked = sorted(self.scores.items(), key=lambda kv: -kv[1])
                board = "\n\n🏁 *Final scores*\n" + "\n".join(f"{n}: {s}/{self.rounds}" for n, s in ranked)
            return f"{prefix}{board}\n\nPlay again with *play {self.key}*."
        return f"{prefix}\n\n" + await self._next()

    async def handle(self, text: str) -> str:
        idx = self._parse(text)
        if idx is None:
            return ""  # unrelated chat (esp. in groups): ignore
        who = self.sender or "You"
        if self.sender_id in self.locked:
            return ""
        if self.choices[idx] == self.q["correct"]:
            self.scores[who] = self.scores.get(who, 0) + 1
            return await self._advance(f"{pick(RIGHT)} *{self.q['correct']}* — {who} gets it!")
        self.locked.add(self.sender_id)
        limit = 3 if self.group_chat else 1
        if len(self.locked) >= limit:
            return await self._advance(f"{pick(WRONG)} The answer was *{self.q['correct']}*.")
        return f"{pick(WRONG)} {who} is out for this question — anyone else?"

    @property
    def finished(self) -> bool:
        return self._done


class Quiz(Trivia):
    key = "quiz"
    title = "Quiz"
    order = 80
    aliases = ("quiz", "quiz me", "quiz game", "quizz", "take a quiz", "start a quiz", "a quiz")
    description = "5 trivia questions"
    rounds = 5
