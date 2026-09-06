"""Massive.com (formerly Polygon.io) Market & Ticker News Client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class MassiveNewsClient:
    """Client for fetching institutional financial headlines from Massive (Polygon.io)."""

    PRIMARY_BASE = "https://api.massive.com"
    FALLBACK_BASE = "https://api.polygon.io"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.effective_massive_api_key

    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("your_"))

    async def fetch_news(self, ticker: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch raw article objects with title, description, publisher, and sentiment."""
        if not self.is_configured():
            return self._offline_articles()

        headers = {"Authorization": f"Bearer {self.api_key}"}
        params: dict[str, Any] = {
            "apiKey": self.api_key,
            "limit": limit,
            "order": "desc",
            "sort": "published_utc",
        }
        if ticker:
            params["ticker"] = ticker

        for base in (self.PRIMARY_BASE, self.FALLBACK_BASE):
            url = f"{base}/v2/reference/news"
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(url, params=params, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    results = data.get("results", [])
                    if results:
                        return results
            except Exception as e:
                logger.warning("Massive news request failed at %s: %s", base, e)
                continue

        logger.error("Failed to fetch news from Massive across all base URLs")
        return self._offline_articles()

    async def headlines(self, ticker: str | None = None, limit: int = 10) -> list[str]:
        """Extract clean headline strings for LLM consensus and sentiment ingestion."""
        articles = await self.fetch_news(ticker=ticker, limit=limit)
        headlines: list[str] = []
        for art in articles:
            title = art.get("title", "").strip()
            if title:
                headlines.append(title)
        return headlines

    @staticmethod
    def _offline_articles() -> list[dict[str, Any]]:
        return [
            {
                "title": "Federal Reserve signals cautious interest rate path as inflation moderates",
                "publisher": {"name": "MarketWatch"},
                "published_utc": "2026-09-02T12:00:00Z",
                "description": "Fed officials emphasize data dependency ahead of next policy meeting.",
            },
            {
                "title": "Crude oil rallies as Middle East supply risks and OPEC quotas tighten market",
                "publisher": {"name": "Bloomberg"},
                "published_utc": "2026-09-02T11:30:00Z",
                "description": "WTI crude futures gain over 1.5% in early trade.",
            },
            {
                "title": "Gold holds steady near record highs on central bank accumulation and hedge flows",
                "publisher": {"name": "Reuters"},
                "published_utc": "2026-09-02T10:45:00Z",
                "description": "Safe-haven bullion demand remains strong amid macroeconomic uncertainties.",
            },
        ]
