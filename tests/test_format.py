from app.format import MAX_LEN, num, numbered, tidy


def test_num_emoji():
    assert [num(1), num(10), num(11)] == ["1️⃣", "🔟", "11."]


def test_numbered_lines():
    assert numbered([("Head", "detail"), ("Plain", "")]) == ["1️⃣ *Head*", "     _detail_", "2️⃣ *Plain*"]


def test_tidy_uses_whatsapp_emphasis_and_cleans_whitespace():
    assert tidy("## Title\n\nSome **bold** text   \n\n\n\nnext") == "*Title*\n\nSome *bold* text\n\nnext"


def test_tidy_leaves_board_layouts_alone():
    board = "❌ ⭕ ❌\n⭕ ❌ ⭕\n  7  8  9"
    assert tidy(board) == board


def test_tidy_cuts_long_replies_at_a_paragraph():
    long = "\n\n".join(f"Paragraph {i} " + "x" * 300 for i in range(40))
    out = tidy(long)
    assert len(out) < MAX_LEN + 40 and out.endswith("… _(shortened)_") and "Paragraph 0" in out
    assert out.split("\n\n")[-2].startswith("Paragraph")                # cut between paragraphs, not mid-word


def test_short_replies_are_untouched():
    assert tidy("pong 🏓") == "pong 🏓"
