# WhatsApp bot (simple)

FastAPI webhook for [WAHA](https://waha.devlike.pro): it receives incoming messages at `POST /webhook` and replies with text.
Drop a folder into `tools/` and the bot picks it up — see [docs/ADDING_A_TOOL.md](docs/ADDING_A_TOOL.md). Routing lives in `app/smart.py`; unmatched messages are echoed.

```bash
cp .env.example .env              # set WAHA_API_KEY
docker compose up -d              # WAHA on :3000 (webhook already points at the bot) — scan the QR code
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --port 8000
.venv/bin/python -m pytest
```

The full modular version (tools, intent engines, games) lives on the `modular-architecture` branch.
