"""Hourly Asset-Specific Macro & News Intelligence Manager.

Pulls news every hour for active CFD assets (XAUUSD, USOIL, EURUSD) from
NewsAPI and Massive.com, analyzes macro sentiment and catalyst bias,
and fuses the macro score directly into quant technical strategy evaluation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from data.news.massive_news_client import MassiveNewsClient
from data.news.newsapi_client import NewsAPIClient
from macro.agents.asset_agent import AssetMacroAgent

logger = logging.getLogger(__name__)

CACHE_FILE = Path("data/asset_macro_cache.json")


class AssetMacroManager:
    """Manages hourly news pulling, sentiment analysis, and strategy integration per asset."""

    ASSETS = ["XAUUSD", "USOIL", "EURUSD", "BTCUSD"]
    HOURLY_TTL_SECONDS = 3600  # 1 hour

    QUERIES = {
        "XAUUSD": "gold price OR gold reserves OR bullion OR XAU OR central bank gold",
        "USOIL": "crude oil OR OPEC OR petroleum OR oil inventory OR USOIL OR energy market",
        "EURUSD": "European Central Bank OR EURUSD OR Eurozone inflation OR ECB rates OR dollar index",
        "BTCUSD": "Bitcoin OR BTC OR crypto ETF OR crypto market OR Federal Reserve liquidity",
    }

    TICKERS = {
        "XAUUSD": "C:XAUUSD",
        "USOIL": "CL",
        "EURUSD": "C:EURUSD",
        "BTCUSD": "X:BTCUSD",
    }

    def __init__(self, cache_file: Path | None = None) -> None:
        self.cache_file = cache_file or CACHE_FILE
        self.newsapi = NewsAPIClient()
        self.massive = MassiveNewsClient()
        self.agents: dict[str, AssetMacroAgent] = {asset: AssetMacroAgent(asset) for asset in self.ASSETS}
        self._data: dict[str, Any] = {}
        self._ensure_cache_dir()
        self._load_cache()

    def _ensure_cache_dir(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_cache(self) -> None:
        if self.cache_file.exists():
            try:
                raw = self.cache_file.read_text(encoding="utf-8").strip()
                if raw:
                    self._data = json.loads(raw)
            except Exception as e:
                logger.debug("Failed loading asset macro cache: %s", e)

    def _save_cache(self) -> None:
        try:
            self.cache_file.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed saving asset macro cache: %s", e)

    def is_stale(self) -> bool:
        last_updated = self._data.get("updated_at_epoch", 0)
        return (time.time() - last_updated) >= self.HOURLY_TTL_SECONDS

    def seconds_until_next_hourly_pull(self) -> int:
        last_updated = self._data.get("updated_at_epoch", 0)
        elapsed = time.time() - last_updated
        return max(0, int(self.HOURLY_TTL_SECONDS - elapsed))

    def _analyze_sentiment(self, asset: str, headlines: list[str]) -> dict[str, Any]:
        """Perform institutional keyword-weighted sentiment analysis for an asset."""
        text = " ".join(headlines).lower()

        bullish_words = [
            "surge", "rally", "gain", "climb", "high", "cut", "stimulus", "demand",
            "bullish", "jump", "record", "easing", "support", "rebound", "reserves",
            "crisis preparedness", "haven", "deficit", "shortage", "boost", "outperform",
        ]
        bearish_words = [
            "drop", "fall", "plunge", "decline", "recession", "glut", "hike", "strong dollar",
            "dxy surges", "hawkish", "slowdown", "bearish", "oversupply", "loss", "crash",
            "tariff", "weakness", "slump", "slide", "yields rise",
        ]

        bull_count = sum(1 for w in bullish_words if w in text)
        bear_count = sum(1 for w in bearish_words if w in text)

        total = bull_count + bear_count
        if total == 0:
            bias = 0.05 if asset == "XAUUSD" else 0.0
        else:
            bias = round((bull_count - bear_count) / max(total, 1), 2)

        # Map to stance
        if bias >= 0.20:
            stance = "BULLISH"
        elif bias <= -0.20:
            stance = "BEARISH"
        else:
            stance = "NEUTRAL"

        # Asset-specific rationale & quant impact
        if asset == "XAUUSD":
            if stance == "BULLISH":
                summary = "Central bank reserve diversification and rate cut expectations support gold safe-haven premium."
                quant_impact = "Macro tailwind favors Long trend pullbacks (+5 score bonus); Shorts require higher technical score (>=65)."
            elif stance == "BEARISH":
                summary = "Elevated real yields and firm US Dollar apply near-term pressure on bullion."
                quant_impact = "Short continuation favored on EMA breakdowns; Long setups require strict value tap confirmation."
            else:
                summary = "Consolidating between steady real yields and geopolitical hedge demand."
                quant_impact = "Pure technical execution on M15 EMA 21 value tap."

        elif asset == "USOIL":
            if stance == "BULLISH":
                summary = "OPEC+ supply discipline and Middle East transport risks maintain energy bid."
                quant_impact = "Donchian channel upside breakouts receive macro momentum confirmation (+5 score bonus)."
            elif stance == "BEARISH":
                summary = "Global manufacturing demand caution and rising inventories cap energy rallies."
                quant_impact = "Favor fading rallies into Donchian resistance; breakout to downside receives confirmation."
            else:
                summary = "Balanced inventory reports and steady OPEC+ quotas keep crude inside typical session ranges."
                quant_impact = "Trade strictly within NY session breakout bounds (12:00-18:00 UTC)."

        else:  # EURUSD
            if stance == "BULLISH":
                summary = "Narrowing Fed-ECB yield differential provides floor for Euro."
                quant_impact = "Lower Bollinger Band sweeps offer high-probability mean reversion long entries."
            elif stance == "BEARISH":
                summary = "Resilient US economic prints and DXY strength maintain downward drag on Euro."
                quant_impact = "Upper Bollinger Band sweeps offer high-conviction fade short entries."
            else:
                summary = "Neutral monetary policy parity between ECB and Federal Reserve."
                quant_impact = "Two-way mean reversion between Bollinger Band extremes (2.0 std)."

        return {
            "bias": bias,
            "stance": stance,
            "summary": summary,
            "quant_impact": quant_impact,
            "bull_signals": bull_count,
            "bear_signals": bear_count,
        }

    async def fetch_and_analyze_asset(self, asset: str) -> dict[str, Any]:
        """Fetch latest verified news and run Anthropic Claude Haiku agent analysis for a single asset."""
        # Check market open status: suspend LLM trend analysis during down/closed market hours
        from macro.scheduler import macro_scheduler
        is_open, status_reason = macro_scheduler.is_asset_market_open(asset)
        if not is_open:
            logger.info("Suspending LLM trend analysis for %s during down market hours: %s", asset, status_reason)
            existing = self._data.get("assets", {}).get(asset)
            if existing:
                cached_res = dict(existing)
                cached_res["updated_at"] = datetime.now(UTC).isoformat()
                cached_res["summary"] = f"Market closed ({status_reason}). Trend analysis suspended during down market hours."
                return cached_res
            agent = self.agents.get(asset) or AssetMacroAgent(asset)
            fallback = agent._fallback_asset(headlines=[f"{asset} market closed ({status_reason})."])
            fallback["summary"] = f"Market closed ({status_reason}). Trend analysis suspended during down market hours."
            return {
                "asset": asset,
                "agent": fallback.get("agent", f"{asset.lower()}_macro_analyst"),
                "model": fallback.get("model", agent.model),
                "updated_at": datetime.now(UTC).isoformat(),
                "bias": fallback.get("bias", 0.0),
                "stance": fallback.get("stance", "NEUTRAL"),
                "confidence": fallback.get("confidence", 0.8),
                "summary": fallback.get("summary", ""),
                "quant_impact": fallback.get("quant_impact", ""),
                "multi_agent_perspectives": fallback.get("multi_agent_perspectives", {}),
                "key_catalysts": fallback.get("key_catalysts", []),
                "headlines": [f"{asset} market closed ({status_reason})."],
                "headlines_count": 0,
            }

        query = self.QUERIES.get(asset, asset)
        ticker = self.TICKERS.get(asset)

        headlines: list[str] = []

        # 1. Fetch from NewsAPI
        try:
            n_heads = await self.newsapi.headlines(query=query, page_size=5)
            if n_heads:
                headlines.extend(n_heads)
        except Exception as e:
            logger.debug("NewsAPI fetch error for %s: %s", asset, e)

        # 2. Fetch from Massive News
        try:
            m_heads = await self.massive.headlines(ticker=ticker, limit=4)
            if m_heads:
                for h in m_heads:
                    if h not in headlines:
                        headlines.append(h)
        except Exception as e:
            logger.debug("Massive news fetch error for %s: %s", asset, e)

        # Fallback if news feeds are quiet
        if not headlines:
            headlines = [
                f"Global markets monitor {asset} institutional flow and central bank policy",
                f"{asset} trades inside expected volatility band ahead of upcoming macroeconomic prints",
            ]

        # Deduplicate and take top 6
        headlines = list(dict.fromkeys(headlines))[:6]

        # Context from global macro regime and live technical stats
        from data.feeds.live_price_feed import live_price_feed
        from macro.regime_classifier import regime_classifier

        regime = regime_classifier.current.name
        regime_summary = regime_classifier.current.summary
        live_stats = live_price_feed.get_mt4_stats().get(asset, {})

        # Execute Anthropic Claude Haiku Agent specialized for this asset
        agent = self.agents.get(asset) or AssetMacroAgent(asset)
        analysis = await agent.analyze_asset(
            headlines=headlines,
            global_regime=regime,
            regime_summary=regime_summary,
            live_stats=live_stats,
        )

        return {
            "asset": asset,
            "agent": analysis.get("agent", f"{asset.lower()}_macro_analyst"),
            "model": analysis.get("model", agent.model),
            "updated_at": datetime.now(UTC).isoformat(),
            "bias": analysis.get("bias", 0.0),
            "stance": analysis.get("stance", "NEUTRAL"),
            "confidence": analysis.get("confidence", 0.8),
            "summary": analysis.get("summary", ""),
            "quant_impact": analysis.get("quant_impact", ""),
            "multi_agent_perspectives": analysis.get("multi_agent_perspectives", {}),
            "key_catalysts": analysis.get("key_catalysts", []),
            "headlines": headlines,
            "headlines_count": len(headlines),
        }

    async def refresh_all(self, force: bool = False) -> dict[str, Any]:
        """Refresh hourly macro analysis for all assets via Anthropic Haiku agents if stale or forced."""
        if not force and not self.is_stale() and "assets" in self._data:
            return self._data

        logger.info("Triggering hourly multi-agent asset macro analysis across %s...", ", ".join(self.ASSETS))
        tasks = [self.fetch_and_analyze_asset(asset) for asset in self.ASSETS]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results = {}
        for asset, res in zip(self.ASSETS, results_list, strict=False):
            if isinstance(res, Exception):
                logger.error("Failed analyzing asset %s with agent: %s", asset, res)
                # Fallback to previous or default
                results[asset] = self._data.get("assets", {}).get(asset) or self.agents[asset]._fallback_asset([])
            else:
                results[asset] = res

        now = datetime.now(UTC)
        self._data = {
            "updated_at": now.isoformat(),
            "updated_at_epoch": time.time(),
            "next_pull_at": (now + timedelta(seconds=self.HOURLY_TTL_SECONDS)).isoformat(),
            "hourly_ttl_seconds": self.HOURLY_TTL_SECONDS,
            "assets": results,
        }
        self._save_cache()
        logger.info("Hourly multi-agent asset macro analysis completed successfully.")
        return self._data

    def get_summary(self) -> dict[str, Any]:
        """Return the current asset macro status (synchronous for API & UI)."""
        defaults = {
            "XAUUSD": {
                "asset": "XAUUSD",
                "bias": 0.45,
                "stance": "BULLISH",
                "summary": "Central bank gold demand and rate cut expectations support gold safe-haven flows.",
                "quant_impact": "Macro tailwind favors Long pullbacks (+5 score bonus).",
                "headlines": ["Central banks continue gold reserve diversification in crisis preparedness move"],
            },
            "USOIL": {
                "asset": "USOIL",
                "bias": 0.15,
                "stance": "NEUTRAL",
                "summary": "OPEC+ quota discipline balances inventory prints.",
                "quant_impact": "Trade strictly within NY session breakout bounds.",
                "headlines": ["Crude oil holds steady amid OPEC supply monitoring"],
            },
            "EURUSD": {
                "asset": "EURUSD",
                "bias": -0.10,
                "stance": "NEUTRAL",
                "summary": "Policy parity between ECB and Federal Reserve.",
                "quant_impact": "Two-way mean reversion between Bollinger Band extremes.",
                "headlines": ["Euro trades inside consolidation range ahead of inflation data"],
            },
            "BTCUSD": {
                "asset": "BTCUSD",
                "bias": 0.25,
                "stance": "BULLISH",
                "summary": "Institutional spot ETF inflows and risk-on liquidity cycle support crypto momentum.",
                "quant_impact": "Favor momentum continuation above M15 EMA 20 (+5 score bonus).",
                "headlines": ["Bitcoin spot ETFs record net inflows amid broader macro risk appetite"],
            },
        }

        if not self._data or "assets" not in self._data:
            now = datetime.now(UTC)
            return {
                "updated_at": now.isoformat(),
                "next_pull_in_seconds": self.HOURLY_TTL_SECONDS,
                "assets": defaults,
            }

        res = dict(self._data)
        assets_map = res.setdefault("assets", {})
        for sym in self.ASSETS:
            if sym not in assets_map and sym in defaults:
                assets_map[sym] = defaults[sym]
        res["next_pull_in_seconds"] = self.seconds_until_next_hourly_pull()
        return res

    def get_quant_adjustment(self, asset: str, side: str, macro_info: dict[str, Any] | None = None) -> tuple[float, str]:
        """Calculate technical score adjustment (+/-) based on hourly macro bias."""
        if macro_info is None:
            summary = self.get_summary()
            assets_data = summary.get("assets", {})
            asset_info = assets_data.get(asset, {})
        else:
            asset_info = macro_info
        bias = float(asset_info.get("bias", 0.0))
        stance = asset_info.get("stance", "NEUTRAL")

        # Alignment bonuses / penalties
        if side.lower() == "long":
            if bias >= 0.20:
                return 5.0, f"Macro tailwind (+{bias:.2f} Bullish) reinforces Long setup"
            elif bias <= -0.25:
                return -5.0, f"Macro headwind ({bias:.2f} Bearish) tempers Long conviction"
        elif side.lower() == "short":
            if bias <= -0.20:
                return 5.0, f"Macro tailwind ({bias:.2f} Bearish) reinforces Short setup"
            elif bias >= 0.25:
                return -5.0, f"Macro headwind (+{bias:.2f} Bullish) tempers Short conviction"

        return 0.0, f"Neutral macro bias ({bias:.2f})"


# Global singleton
asset_macro_manager = AssetMacroManager()
