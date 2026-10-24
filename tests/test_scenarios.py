"""Runs every scripted conversation against the real tools with realistic (offline) upstream data."""
import pytest

from tests import api_fixtures as F
from tests.helpers import make_bot
from tests.scenarios import conversations, games
from tests.scenarios.dsl import play

ALL = [*conversations.ALL, *games.SCENARIOS]


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


@pytest.mark.parametrize("scenario", ALL, ids=[s.name for s in ALL])
async def test_scenario(scenario, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_CSE_ID", "c")
    clock = Clock()
    bot, http = make_bot(F.routes(), clock=clock)
    await play(scenario, bot, http, clock)
