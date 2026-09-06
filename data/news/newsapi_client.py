"""NewsAPI client with offline headlines fallback."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class NewsAPIClient:
    BASE = "https://newsapi.org/v2/everything"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.newsapi_key

    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("your_"))

    async def headlines(self, query: str = "federal reserve OR inflation OR OPEC", page_size: int = 10) -> list[str]:
        if not self.is_configured():
            return [
                "Fed holds rates steady amid sticky inflation",
                "OPEC+ signals cautious supply stance",
                "Treasury yields ease as growth concerns mount",
            ]
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    self.BASE,
                    params={
                        "q": query,
                        "pageSize": page_size,
                        "sortBy": "publishedAt",
                        "language": "en",
                        "apiKey": self.api_key,
                    },
                )
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return [a.get("title", "") for a in data.get("articles", []) if a.get("title")]
        except Exception:
            logger.exception("NewsAPI fetch failed")
            return []
