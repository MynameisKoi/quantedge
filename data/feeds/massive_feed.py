"""Massive.com (formerly Polygon.io) REST feed adapter."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class MassiveFeed:
    """REST feed client for Massive.com (formerly Polygon.io)."""

    PRIMARY_BASE = "https://api.massive.com"
    FALLBACK_BASE = "https://api.polygon.io"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.effective_massive_api_key
        self.base_url = base_url or self.PRIMARY_BASE

    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("your_"))

    async def last_quote(self, symbol: str) -> dict[str, Any]:
        if not self.is_configured():
            return self._stub(symbol)

        clean_sym = symbol.replace("/", "").upper()
        # For Forex / CFD pairs (e.g. EURUSD, XAUUSD)
        is_fx = len(clean_sym) == 6 and clean_sym in ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD")
        
        for base in (self.base_url, self.FALLBACK_BASE):
            if is_fx:
                from_curr, to_curr = clean_sym[:3], clean_sym[3:]
                url = f"{base}/v1/last_quote/currencies/{from_curr}/{to_curr}"
            else:
                url = f"{base}/v2/aggs/ticker/C:{clean_sym}/prev"

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(url, params={"apiKey": self.api_key})
                    if resp.status_code == 200:
                        data = resp.json()
                        return data
            except Exception as e:
                logger.debug("Massive quote attempt at %s for %s: %s", base, symbol, e)
                continue

        return self._stub(symbol)

    async def news(self, ticker: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch institutional ticker and market news from Massive / Polygon."""
        if not self.api_key:
            return []

        params: dict[str, Any] = {
            "apiKey": self.api_key,
            "limit": limit,
            "order": "desc",
            "sort": "published_utc",
        }
        if ticker:
            params["ticker"] = ticker

        for base in (self.base_url, self.FALLBACK_BASE):
            url = f"{base}/v2/reference/news"
            try:
                async with httpx.AsyncClient(timeout=12) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    results = data.get("results", [])
                    return results
            except Exception as e:
                logger.warning("Massive news fetch attempt at %s failed: %s", base, e)
                continue

        return []

    @staticmethod
    def _stub(symbol: str) -> dict[str, Any]:
        stubs = {
            "XAUUSD": 2350.0,
            "USOIL": 78.5,
            "BTCUSD": 65000.0,
            "EURUSD": 1.085,
        }
        px = stubs.get(symbol, 100.0)
        return {"status": "stub", "symbol": symbol, "price": px}
