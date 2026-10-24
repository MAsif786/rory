"""Shared services handed to tools via ctx.services (so tools never build their own HTTP client)."""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()


class Services:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=12, follow_redirects=True,
                # Wikimedia's robot policy wants contact info in the UA; set BOT_CONTACT (URL or email) in .env
                headers={"User-Agent": f"rory/1.0 ({os.getenv('BOT_CONTACT', 'https://github.com/MAsif786/rory')})"})
        return self._http
