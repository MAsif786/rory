"""The improvement inbox: a durable record of every message Rory could not handle, so they can be reviewed and taught later.

Recorded (one JSON object per line in `data/unmatched.jsonl`, never committed):
  unmatched    nothing understood the message
  tool_error   a tool failed (generic / network error) for a message that WAS understood
Chat ids are stored only as a short hash; the message text is kept (it is what you need to improve the bot) and pruned after
UNMATCHED_RETENTION_DAYS. Review with `scripts/unmatched.py`."""
import difflib
import json
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.logsetup import chat_ref


class Recorder:
    """Appends entries to a JSONL file. Never raises: the inbox must not be able to break a conversation."""

    def __init__(self, path: str | Path | None, clock: Callable[[], float] = time.time) -> None:
        self.path = Path(path) if path else None
        self.clock, self._lock = clock, threading.Lock()

    def record(self, kind: str, text: str, chat_id: str, *, feature: str | None = None, nearest: str | None = None, note: str | None = None) -> None:
        if not self.path or not text.strip():
            return
        entry = {"ts": round(self.clock(), 3), "kind": kind, "text": text.strip()[:300], "chat": chat_ref(chat_id), "group": chat_id.endswith("@g.us"),
                 "feature": feature, "nearest": nearest, "note": note}
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def read(self) -> list[dict]:
        return read_entries(self.path) if self.path else []

    def prune(self, days: float) -> int:
        """Drop entries older than `days`; returns how many were removed."""
        if not self.path or not self.path.exists():
            return 0
        entries, cutoff = read_entries(self.path), self.clock() - days * 86400
        keep = [e for e in entries if e.get("ts", 0) >= cutoff]
        with self._lock:
            self.path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in keep), encoding="utf-8")
        return len(entries) - len(keep)


def read_entries(path: str | Path | None) -> list[dict]:
    if not path or not Path(path).exists():
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue                                   # a half-written line must never break the review tool
    return out


# --- analysis -----------------------------------------------------------------------------------------------------------------
def normalise(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s']", " ", text.lower()).split())


@dataclass
class Group:
    text: str                                          # normalised message
    sample: str                                        # one original spelling
    count: int = 0
    chats: set = field(default_factory=set)
    kinds: set = field(default_factory=set)
    features: set = field(default_factory=set)
    first: float = 0
    last: float = 0
    nearest: str | None = None                         # closest known example
    suggested: str | None = None                       # feature that example belongs to


def nearest_example(text: str, specs, cutoff: float = 0.6) -> tuple[str, str] | None:
    examples = {ex.lower(): s.full_name for s in specs for ex in s.examples}
    close = difflib.get_close_matches(normalise(text), list(examples), n=1, cutoff=cutoff)
    return (close[0], examples[close[0]]) if close else None


def group_entries(entries: list[dict], specs=(), reviewed: set[str] = frozenset(), since: float = 0, kinds: set[str] | None = None) -> list[Group]:
    """Collapse repeats ('Hello?', 'hello') into one row with a count, newest information last, most frequent first."""
    groups: dict[str, Group] = {}
    for e in entries:
        key = normalise(e.get("text", ""))
        if not key or key in reviewed or e.get("ts", 0) < since or (kinds and e.get("kind") not in kinds):
            continue
        g = groups.setdefault(key, Group(key, e["text"], first=e["ts"], last=e["ts"]))
        g.count += 1
        g.chats.add(e.get("chat"))
        g.kinds.add(e.get("kind"))
        if e.get("feature"):
            g.features.add(e["feature"])
        g.first, g.last = min(g.first, e["ts"]), max(g.last, e["ts"])
    for g in groups.values():
        if specs and (near := nearest_example(g.text, specs)):
            g.nearest, g.suggested = near
    return sorted(groups.values(), key=lambda g: (-g.count, -g.last))


def load_reviewed(path: str | Path) -> set[str]:
    p = Path(path)
    try:
        return set(json.loads(p.read_text())) if p.exists() else set()
    except ValueError:
        return set()


def save_reviewed(path: str | Path, reviewed: set[str]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(sorted(reviewed), ensure_ascii=False, indent=0))


def corpus_lines(groups: list[Group]) -> str:
    """Ready-to-paste lines for tests/corpus/intents.py (GAPS format: text, expected feature, reason). Review the guesses!"""
    out = ["# paste into GAPS in tests/corpus/intents.py, fix the expected feature (None = should be ignored) and the reason"]
    for g in groups:
        guess = f'"{g.suggested}"' if g.suggested else "None"
        why = f"seen {g.count}x" + (f"; nearest example {g.nearest!r}" if g.nearest else "") + (f"; tool failed ({', '.join(sorted(g.features))})" if "tool_error" in g.kinds else "")
        out.append(f'    ({json.dumps(g.sample, ensure_ascii=False)}, {guess}, "{why}"),')
    return "\n".join(out)
