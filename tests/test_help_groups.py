"""Help is organised into groups (Everyday, Look things up, Quran, Web & dev, Just for fun, Games, Chat) instead of one long list."""
import pytest

from app import replies
from app.core.registry import Registry
from app.core.tool import Tool
from tests.helpers import lint_reply, make_bot, real_registry

REG = real_registry()
KEYS = [c[0] for c in replies.CATEGORIES]


VISIBLE = [c for c in KEYS if any(t.category == c and not t.hidden for t in REG.tools.values())]       # groups that have a listed tool


def test_every_installed_tool_belongs_to_a_known_group():
    """A tool added without `category=` would land in 'More'. That is safe, but an author should choose: this fails until they do."""
    stray = sorted(t.name for t in REG.tools.values() if t.category not in KEYS)
    assert not stray, f"set Tool(..., category=...) to one of {KEYS} for: {stray}"


def test_the_home_page_is_short():
    home = replies.home_menu(REG)
    assert len(home.splitlines()) <= 22 and len(home) <= 1200, f"{len(home.splitlines())} lines, {len(home)} chars"
    assert home.startswith("🏠 *Home*") and "help <group>" not in home                # no "how to use help" hint: the page speaks for itself
    assert "💡" not in home


def test_every_group_with_tools_is_on_the_home_page_and_nothing_is_under_more():
    groups = replies.grouped(REG)
    assert [c[0] for c, _ in groups] == VISIBLE == ["everyday", "knowledge", "islamic", "web", "entertainment", "games"]   # in menu order, none in "More"
    home = replies.home_menu(REG)
    for (key, emoji, title, *_), tools in groups:
        assert f"{emoji} *{title}*" in home


def test_every_tool_is_in_exactly_one_group_page():
    seen = {}
    for cat, tools in replies.grouped(REG):
        for t in tools:
            assert t.name not in seen, f"{t.name} is in two groups"
            seen[t.name] = cat[0]
    assert set(seen) == {n for n, t in REG.tools.items() if not t.hidden}
    for name, key in seen.items():
        page = replies.help_for(REG, key)
        assert REG.tools[name].title in page or key == "games", f"{name} missing from the {key} page"


@pytest.mark.parametrize("word, expected", [
    ("everyday", "Weather"), ("tools", "Weather"), ("daily", "Weather"), ("knowledge", "Wikipedia"), ("lookup", "Wikipedia"), ("learn", "Wikipedia"),
    ("web", "GitHub"), ("dev", "GitHub"), ("developer", "GitHub"), ("islamic", "Quran"), ("islam", "Quran"), ("entertainment", "Jokes"),
    ("play", "Blackjack"), ("games", "Blackjack"), ("Look things up", "Wikipedia"), ("EVERYDAY", "Weather"), ("!everyday", "Weather")])
def test_help_opens_a_group_by_key_title_or_alias(word, expected):
    assert expected in replies.help_for(REG, word)


@pytest.mark.parametrize("word", ["fun", "quran", "dice", "weather", "news", "wiki"])
def test_a_tools_own_name_wins_over_a_group_word(word):
    page = replies.help_for(REG, word)
    assert f"{word}." in page                                          # a tool page lists its features as "tool.feature"


def test_group_pages_show_each_tool_with_examples_and_point_to_the_next_level():
    page = replies.help_for(REG, "everyday")
    assert page.startswith("🌤️ *Everyday*") and "_weather in lahore" in page
    assert "💡" not in page and "goes back" not in page                             # no navigation hints
    assert len(page.splitlines()) <= 25


def test_help_all_is_a_complete_grouped_index_that_fits_in_one_message():
    allp = replies.help_for(REG, "all")
    positions = [allp.index(f"━━ {c[1]} *{c[2].upper()}* ━━") for c, _ in replies.grouped(REG)]
    assert positions == sorted(positions)                                       # headings in menu order
    assert len(allp) < 3800 and not lint_reply(allp), len(allp)                 # never cut off by the message length cap
    for t in (t for t in REG.tools.values() if not t.hidden):                    # ... yet nothing listed is missing: every tool and every feature name
        assert t.title in allp
        assert all(f.spec.name.replace("_", " ") in allp for f in t.features.values()), t.name


def test_unknown_group_tool_or_feature():
    assert "No group, tool or feature called *nope*" in replies.help_for(REG, "nope")


def test_every_help_page_is_clean():
    pages = ["", "all", "more", *KEYS, *[c for cat in replies.CATEGORIES for c in cat[4]], *REG.tools, *[s.full_name for s in REG.specs()]]
    for arg in pages:
        text = replies.help_for(REG, arg)
        assert not lint_reply(text), (arg, lint_reply(text))


# --- tools without a (known) category --------------------------------------------------------------------------------------------
def make_registry(**categories):
    reg = Registry()
    for name, category in categories.items():
        t = Tool(name, title=name.title(), category=category)

        @t.feature("go", phrases=[f"do {name}"], examples=[f"do {name}"], description=f"{name} thing")
        async def go(ctx): ...
        reg.add(t, name)
    return reg


def test_unknown_or_missing_categories_go_under_more_and_stay_reachable():
    reg = make_registry(alpha="", beta="no-such-group", gamma="everyday")
    groups = {c[0]: [t.name for t in tools] for c, tools in replies.grouped(reg)}
    assert groups == {"everyday": ["gamma"], "other": ["alpha", "beta"]}
    home = replies.home_menu(reg)
    assert "🧩 *More* — Alpha · Beta" in home and "🌤️ *Everyday* — gamma" not in home and "🌤️ *Everyday*" in home
    assert "Alpha" in replies.help_for(reg, "more") and "Beta" in replies.help_for(reg, "more")


def test_the_order_inside_a_group_is_most_useful_first():
    assert [t.name for t in dict((c[0], tools) for c, tools in replies.grouped(REG))["everyday"]] == ["weather", "news", "currency", "units", "calc", "clock"]


def test_a_new_tool_appears_without_touching_core(make_tools):
    root, pkg = make_tools({"tarot": '''
from app.core.tool import Tool
tool = Tool("tarot", title="Tarot", emoji="🔮", description="Draw a card", category="entertainment")
@tool.feature("draw", phrases=["draw a card"], examples=["draw a card"])
async def draw(ctx): return "The Fool"
'''})
    reg = Registry().discover(root, pkg)
    assert "Draw a card" in replies.home_menu(reg) and "Tarot" in replies.help_for(reg, "entertainment")          # a lone tool says what it does


# --- through the bot --------------------------------------------------------------------------------------------------------------
async def test_help_groups_work_in_chat_and_mid_game():
    bot, _ = make_bot({})
    assert "Weather" in await bot.respond("c", "help everyday")
    assert "Wikipedia" in await bot.respond("c", "help lookup")
    await bot.respond("c", "play hangman")
    assert "Blackjack" in await bot.respond("c", "help games")             # help never ends a game
    assert bot.store.get("c").session.tool == "hangman"
    assert "Home" in await bot.respond("c", "menu")


# --- brevity, links, hidden tools ------------------------------------------------------------------------------------------------
def test_descriptions_are_short():
    long_tools = {t.name: t.description for t in REG.tools.values() if len(t.description) > 30}
    long_features = {s.full_name: s.description for s in REG.specs() if len(s.description) > 50}
    assert not long_tools, f"tool descriptions over 30 chars (they show on the home and group pages): {long_tools}"
    assert not long_features, f"feature descriptions over 50 chars (they show on tool pages): {long_features}"


def test_a_description_that_only_repeats_the_title_is_not_shown():
    page = replies.help_for(REG, "web")
    assert "*Web search*\n" in page + "\n" and "Web search — Web search" not in page and "Link preview — Link previews" not in page
    assert "🐙 *GitHub* — Repos & search" in page                                  # a description that adds something stays


LINKISH = ("http://", "https://", "www.", "example.com", ".com")


def test_no_help_page_shows_something_that_looks_like_a_link():
    """Chat apps turn a URL into a clickable preview; examples that are links stay in the tool (the tests use them) but are never displayed."""
    pages = [replies.help_for(REG, a) for a in ["", "all", *KEYS, *REG.tools, *[s.full_name for s in REG.specs()]]]
    pages += [replies.not_understood(REG, 1, t) for t in ("blah blah blah blah", "summarize something please now ok", "exampel dot com")]
    for page in pages:
        assert not any(bad in page for bad in LINKISH), [bad for bad in LINKISH if bad in page]


def test_the_link_tool_still_has_url_examples_for_the_tests_but_hides_them():
    spec = next(s for s in REG.specs() if s.full_name == "link.peek")
    assert any("https://" in e for e in spec.examples) and replies.shown(spec.examples) == []


def test_a_did_you_mean_never_suggests_a_link():
    for text in ("htps example com", "summarise exmple.com", "tech of exampel"):
        assert "example" not in replies.not_understood(REG, 1, text).lower() or "Did you mean" not in replies.not_understood(REG, 1, text)


def test_hidden_tools_are_not_listed_but_still_work_and_can_be_opened_by_name():
    greetings = REG.tools["greetings"]
    assert greetings.hidden
    for page in (replies.help_for(REG, ""), replies.help_for(REG, "all"), replies.help_for(REG, "chat")):
        assert "Greetings" not in page and "Small talk" not in page and "💬" not in page
    assert "greetings.hello" in replies.help_for(REG, "greetings")                    # asking for it by name still works


async def test_hidden_tools_keep_working_in_chat():
    bot, _ = make_bot({})
    assert "Rory" in await bot.respond("c", "hi") and "Wa alaikum" in await bot.respond("c2", "assalamualaikum")


def test_the_fallback_capability_line_does_not_mention_hidden_tools():
    line = replies.classify_unmatched(REG, 1, "order me a pizza").reply
    assert "greetings" not in line.lower() and "small talk" not in line.lower()
