"""Regime state tracking with multi-agent consensus."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from data.news.massive_news_client import MassiveNewsClient
from data.news.newsapi_client import NewsAPIClient
from macro.agents import CommodityAgent, DovishAgent, HawkishAgent, PortfolioManagerAgent
from macro.cache import macro_cache

logger = logging.getLogger(__name__)


@dataclass
class RegimeState:
    name: str = "risk-on"
    confidence: float = 0.0
    summary: str = ""
    debates: list[dict[str, Any]] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "regime": self.name,
            "confidence": self.confidence,
            "summary": self.summary,
            "debates": self.debates,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class RefreshResult:
    state: RegimeState
    changed: bool

    def as_dict(self) -> dict[str, Any]:
        data = self.state.as_dict()
        data["changed"] = self.changed
        return data


class RegimeClassifier:
    def __init__(self) -> None:
        self.hawkish = HawkishAgent()
        self.dovish = DovishAgent()
        self.commodity = CommodityAgent()
        self.pm = PortfolioManagerAgent()
        self.current = RegimeState()
        self._context: dict[str, Any] = {"headlines": [], "calendar": []}

    def update_context(self, headlines: list[str] | None = None, calendar: list[Any] | None = None) -> None:
        if headlines is not None:
            self._context["headlines"] = headlines
        if calendar is not None:
            self._context["calendar"] = calendar

    async def fetch_live_news(self) -> list[str]:
        """Automatically pull fresh financial and macro news from configured providers."""
        headlines: list[str] = []
        try:
            newsapi = NewsAPIClient()
            if newsapi.is_configured():
                api_headlines = await newsapi.headlines(query="Federal Reserve OR inflation OR interest rates OR oil OR gold", page_size=8)
                for item in api_headlines:
                    title = item if isinstance(item, str) else (item.get("title", "") if isinstance(item, dict) else "")
                    if title:
                        headlines.append(title)
        except Exception as e:
            logger.warning("Auto news fetch from NewsAPI failed: %s", e)

        try:
            massive = MassiveNewsClient()
            if massive.is_configured():
                massive_articles = await massive.headlines(limit=8)
                for item in massive_articles:
                    title = item if isinstance(item, str) else (item.get("title", "") if isinstance(item, dict) else "")
                    if title:
                        headlines.append(title)
        except Exception as e:
            logger.warning("Auto news fetch from Massive failed: %s", e)

        # Deduplicate preserving order
        seen = set()
        deduped = []
        for h in headlines:
            cleaned = h.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                deduped.append(cleaned)

        if deduped:
            logger.info("Automatically pulled %d live macro headlines from NewsAPI/Massive.", len(deduped))
            self._context["headlines"] = deduped
        return deduped

    async def refresh(self, force: bool = False) -> RefreshResult:
        previous = self.current.name

        # 1. Check 24-Hour Model Output Cache
        if not force:
            cached = macro_cache.load()
            if cached is not None:
                self.current = RegimeState(
                    name=cached.regime,
                    confidence=cached.confidence,
                    summary=f"[24h Cached Consensus - {cached.remaining_hours()}h left] {cached.summary}",
                    debates=cached.debates,
                    updated_at=datetime.fromisoformat(cached.cached_at),
                )
                changed = previous != self.current.name
                return RefreshResult(state=self.current, changed=changed)

        # 2. Automated First-Run News Ingestion if context is empty
        if not self._context.get("headlines"):
            await self.fetch_live_news()

        context = {
            **self._context,
            "as_of": datetime.now(UTC).isoformat(),
        }

        # 3. Query LLM Multi-Agent Debate
        debates = [
            await self.hawkish.analyze(context),
            await self.dovish.analyze(context),
            await self.commodity.analyze(context),
        ]
        decision = self.pm.synthesize(debates)

        # 4. Save to 24-Hour Cache to minimize API costs
        macro_cache.save(
            regime=decision["regime"],
            confidence=float(decision["confidence"]),
            summary=decision["summary"],
            debates=decision["debates"],
            headlines_count=len(self._context.get("headlines", [])),
        )

        self.current = RegimeState(
            name=decision["regime"],
            confidence=float(decision["confidence"]),
            summary=decision["summary"],
            debates=decision["debates"],
            updated_at=datetime.now(UTC),
        )
        changed = previous != self.current.name
        if changed:
            logger.info("Macro regime: %s → %s", previous, self.current.name)
        return RefreshResult(state=self.current, changed=changed)


# Shared classifier for API reads.
regime_classifier = RegimeClassifier()
