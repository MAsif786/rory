import asyncio

from tools._template.tool import tool


def test_greet():
    assert asyncio.run(tool.features["greet"].handler(None, "sara")) == "Hello Sara!"
