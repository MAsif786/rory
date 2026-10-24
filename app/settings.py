"""All configuration in one validated object. A bad value stops the bot at startup with a message that says what to fix."""
import os
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator

load_dotenv()


class SettingsError(RuntimeError):
    """Raised at startup when the environment is misconfigured; the message lists every problem."""


class Settings(BaseModel):
    waha_url: str = "http://localhost:3000"
    waha_api_key: str = ""
    bot_name: str = "rory"                                  # what people type to address the bot in a group ("rory weather in lahore")
    group_mode: Literal["mention", "all", "off"] = "mention"   # groups: answer only when addressed / answer everything / ignore groups
    rate_limit_max: int = Field(12, ge=1)                   # messages allowed per sender ...
    rate_limit_window: float = Field(30, gt=0)              # ... per this many seconds
    dedup_ttl: float = Field(300, gt=0)                     # seconds a WAHA message id is remembered (retries / double webhooks)
    chat_idle_ttl: float = Field(3600, gt=0)                # forget a chat's state after this many idle seconds
    max_chats: int = Field(10_000, ge=10)                   # hard cap on remembered chats (least recently used go first)
    max_message_chars: int = Field(1000, ge=10)             # longer messages get a polite refusal instead of being processed
    unmatched_path: str = "data/unmatched.jsonl"            # the improvement inbox: messages Rory could not handle ("" turns it off)
    unmatched_retention_days: float = Field(30, gt=0)       # entries older than this are pruned at startup
    log_json: bool = True                                   # one JSON object per log line (False: readable text for local dev)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("waha_url")
    @classmethod
    def _url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("bot_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip().lower()
        if not v.isalnum():
            raise ValueError("must be a single word (letters and digits)")
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def _level(cls, v):
        return v.upper() if isinstance(v, str) else v

    @field_validator("group_mode", mode="before")
    @classmethod
    def _mode(cls, v):
        return v.lower() if isinstance(v, str) else v

    @classmethod
    def from_env(cls, env=None) -> "Settings":
        env = os.environ if env is None else env
        raw = {name: env[name.upper()] for name in cls.model_fields if name.upper() in env and env[name.upper()] != ""}
        try:
            return cls(**raw)
        except ValidationError as e:
            problems = "\n".join(f"  - {err['loc'][0].upper()}={raw.get(err['loc'][0])!r}: {err['msg']}" for err in e.errors())
            raise SettingsError(f"Invalid configuration (.env / environment):\n{problems}") from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
