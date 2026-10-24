import itertools
import sys
import textwrap

import pytest

_n = itertools.count()


@pytest.fixture
def make_tools(tmp_path, monkeypatch):
    """make_tools({"weather": "<tool.py source>"}) -> (path, package) for Registry().discover(path, package)."""
    monkeypatch.syspath_prepend(str(tmp_path))

    def build(tools: dict[str, str]):
        pkg = f"fake_tools_{next(_n)}"
        root = tmp_path / pkg
        root.mkdir()
        (root / "__init__.py").write_text("")
        for name, src in tools.items():
            (root / name).mkdir()
            (root / name / "__init__.py").write_text("")
            (root / name / "tool.py").write_text(textwrap.dedent(src))
        return root, pkg
    return build


@pytest.fixture(autouse=True)
def fresh_greeting_memory():
    """The greetings tool remembers (in memory) who it greeted recently; every test starts with a clean slate."""
    from tools.greetings import tool as greetings
    greetings._last.clear()
