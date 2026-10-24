# Rory

*A little help, wherever you chat.*

A modular, rule-based chat companion that connects messaging platforms with useful tools, everyday assistance, and games — without requiring an LLM.
Rory is extensible and platform-independent, with pluggable tools, built-in games, and a replaceable intent engine.

Today Rory talks through [WAHA](https://waha.devlike.pro) (WhatsApp): messages arrive at `POST /webhook` and replies go back as text.
Drop a folder into `tools/` and Rory picks it up — see [docs/ADDING_A_TOOL.md](docs/ADDING_A_TOOL.md). Routing lives in `app/smart.py`; send *help* to see what's installed.

```bash
cp .env.example .env              # set WAHA_API_KEY
docker compose up -d              # WAHA on :3000 (webhook already points at the bot) — scan the QR code
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --port 8000 --reload   # restarts on code changes
.venv/bin/python -m pytest
```

The earlier full version (tools, intent engines, games) lives on the `modular-architecture` branch.
