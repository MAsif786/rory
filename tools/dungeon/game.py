import random
from dataclasses import dataclass, field

from app.fun import pick
from app.games import Game

DIRS = ["left", "forward", "right"]
ARROW = {"left": "⬅️", "forward": "⬆️", "right": "➡️"}
ALIASES = {
    "l": "left", "left": "left",
    "r": "right", "right": "right",
    "f": "forward", "forward": "forward", "ahead": "forward", "straight": "forward",
    "b": "back", "back": "back",
}
LIVES, KEYS_NEEDED, KEYS_TOTAL, TRAPS = 3, 2, 3, 3

ROOM_DESC = [
    "A damp stone chamber. Water drips somewhere in the dark.",
    "A round room with cracked statues staring at you.",
    "Cobwebs everywhere. Something skittered away as you entered.",
    "A narrow hall lit by a single flickering torch.",
    "Old bones are scattered across the floor. Charming.",
    "A mossy cellar that smells like regret.",
    "A vaulted room with faded murals of long-dead kings.",
    "Rusty chains hang from the ceiling and sway gently. No wind, though...",
]
KEY_MSG = ["🗝️ You found a rusty key! Pocketed.", "🗝️ A key glints in a crack in the wall. Yours now!"]
TRAP_MSG = [
    "💥 Click! A dart trap! You lose a life.",
    "🕳️ The floor gives way — you scrape out of a pit. You lose a life.",
    "🔥 Flames burst from the wall! You lose a life.",
]


@dataclass
class Room:
    id: int
    layer: int
    kind: str = "empty"          # empty | key | trap | start | exit
    desc: str = ""
    exits: dict[str, int] = field(default_factory=dict)
    used: bool = False           # key taken / trap sprung


def generate() -> list[Room]:
    sizes = [1, random.randint(2, 3), random.randint(2, 3), random.randint(2, 3), random.randint(1, 2), 1]
    layers: list[list[Room]] = []
    rooms: list[Room] = []
    for li, n in enumerate(sizes):
        layer = []
        for _ in range(n):
            r = Room(len(rooms), li, desc=random.choice(ROOM_DESC))
            rooms.append(r)
            layer.append(r)
        layers.append(layer)

    def link(parent: Room, child: Room) -> None:
        if child.id in parent.exits.values() or len(parent.exits) >= 3:
            return
        parent.exits[random.choice([d for d in DIRS if d not in parent.exits])] = child.id

    for cur, nxt in zip(layers, layers[1:]):
        for p in cur:
            link(p, random.choice(nxt))
        for c in nxt:  # every room must be reachable
            if not any(c.id in p.exits.values() for p in cur):
                link(random.choice([p for p in cur if len(p.exits) < 3]), c)
        for p in cur:  # a few extra paths so the map isn't a straight line
            if random.random() < 0.5:
                link(p, random.choice(nxt))

    rooms[0].kind, rooms[0].desc = "start", "The cell door creaks open. Cold air. You're free-ish... now find the way out."
    rooms[-1].kind, rooms[-1].desc = "exit", "A massive iron door, glowing with a faint light. Two keyholes stare back at you."
    mid = [r for r in rooms if r.kind == "empty"]
    random.shuffle(mid)
    for r in mid[:KEYS_TOTAL]:
        r.kind = "key"
    for r in mid[KEYS_TOTAL:KEYS_TOTAL + TRAPS]:
        r.kind = "trap"
    return rooms


class EscapeDungeon(Game):
    key = "dungeon"
    title = "Escape the Dungeon"
    order = 60
    aliases = ("dungeon", "escape the dungeon", "escape dungeon", "dungeon escape", "dungeon game", "adventure game", "escape room")
    description = "Explore rooms, grab keys, dodge traps, escape. Go left, right or forward."

    def __init__(self) -> None:
        self.rooms = generate()
        self.here = 0
        self.history: list[int] = []
        self.keys = 0
        self.lives = LIVES
        self._done = False

    @property
    def room(self) -> Room:
        return self.rooms[self.here]

    def _hud(self) -> str:
        return f"{'❤️' * self.lives}{'🖤' * (LIVES - self.lives)}  🗝️ {self.keys}/{KEYS_NEEDED}"

    def _describe(self) -> str:
        r = self.room
        lines = [f"🕯️ {r.desc}", ""]
        for d in DIRS:
            if d in r.exits:
                lines.append(f"{ARROW[d]} {d}")
        if r.kind == "exit":
            lines.append("🚪 *open* the door")
        if self.history:
            lines.append("🔙 back")
        hints = []
        for d, rid in r.exits.items():
            k = self.rooms[rid]
            if k.kind == "trap" and not k.used:
                hints.append(f"⚠️ Faint clicking from the {d} passage...")
            elif k.kind == "key" and not k.used:
                hints.append(f"✨ Something glints down the {d} passage.")
        if hints:
            lines += [""] + hints
        lines += ["", self._hud()]
        return "\n".join(lines)

    def start(self) -> str:
        return (
            f"🗝️ *{self.title}*\nFind {KEYS_NEEDED} keys, open the iron door, and escape — "
            "but watch out for traps!\nCommands: *left / forward / right / back* (or l/f/r/b), *look*. "
            "*reset* new dungeon, *quit* to stop.\n\n" + self._describe()
        )

    def _enter(self, rid: int) -> str:
        self.here = rid
        r = self.room
        event = ""
        if r.kind == "key" and not r.used:
            r.used = True
            self.keys += 1
            event = pick(KEY_MSG) + "\n\n"
        elif r.kind == "trap" and not r.used:
            r.used = True
            self.lives -= 1
            event = pick(TRAP_MSG) + "\n\n"
            if self.lives <= 0:
                self._done = True
                return f"{event}💀 The dungeon claims another soul. *play dungeon* to try again."
        return event + self._describe()

    def handle(self, text: str) -> str:
        text = text.strip().lower()
        if text == "reset":
            self.__init__()
            return "🔄 The dungeon shifts and rearranges itself...\n\n" + self._describe()
        if text in ("look", "map", "keys", "inv", "inventory"):
            return self._describe()

        r = self.room
        if text in ("open", "door", "unlock") and r.kind == "exit":
            if self.keys >= KEYS_NEEDED:
                self._done = self.won = True
                return "🔓 Click, click... the door groans open and daylight floods in!\n\n🎉 *YOU ESCAPED!* *play dungeon* for a new dungeon."
            return f"🔒 Locked. You need {KEYS_NEEDED} keys, you have {self.keys}. Go find more!"

        move = ALIASES.get(text)
        if not move:
            return "🤔 Try *left*, *forward*, *right*, *back*, *look*" + (" or *open*." if r.kind == "exit" else ".")
        if move == "back":
            if not self.history:
                return "🧱 Nothing behind you but the cell wall."
            return self._enter(self.history.pop())
        if move not in r.exits:
            return f"🧱 Solid wall to the {move}. Pick another way.\n\n{self._describe()}"
        self.history.append(self.here)
        return self._enter(r.exits[move])

    @property
    def finished(self) -> bool:
        return self._done
