"""Shared services handed to tools via ctx.services (so tools never build their own HTTP client)."""
import httpx


class Services:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=10)
        return self._http
