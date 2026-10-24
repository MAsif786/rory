"""Logging: one JSON object per line in production (easy to grep, ship and analyse), readable text for local development.
Chat ids are phone numbers, so logs carry a short hash (`chat`) instead; the raw id never reaches the log file."""
import hashlib
import json
import logging
from datetime import datetime, timezone

RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}


def chat_ref(chat_id: str) -> str:
    return hashlib.sha1(chat_id.encode()).hexdigest()[:10]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"), "level": record.levelname,
                "logger": record.name, "msg": record.getMessage()}
        data.update({k: v for k, v in record.__dict__.items() if k not in RESERVED})
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extra = " ".join(f"{k}={v}" for k, v in record.__dict__.items() if k not in RESERVED)
        base = f"{record.levelname}:{record.name}:{record.getMessage()}" + (f"  [{extra}]" if extra else "")
        return base + ("\n" + self.formatException(record.exc_info) if record.exc_info else "")


def setup_logging(json_logs: bool = True, level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if json_logs else TextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)           # one line per upstream call is noise at INFO
