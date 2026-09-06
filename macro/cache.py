"""24-Hour Macro Consensus Model Output Cache.

Prevents redundant LLM API calls by caching macro regime consensus and multi-agent
debates on disk. Valid for 24 hours by default, slashing API model costs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CACHE_FILE = Path("data/macro_cache.json")


@dataclass
class CachedMacroDecision:
    cached_at: str
    expires_at: str
    regime: str
    confidence: float
    summary: str
    debates: list[dict[str, Any]]
    headlines_count: int

    def is_valid(self) -> bool:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(UTC) < exp
        except Exception:
            return False

    def remaining_hours(self) -> float:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            rem = (exp - datetime.now(UTC)).total_seconds() / 3600.0
            return max(0.0, round(rem, 2))
        except Exception:
            return 0.0


class MacroCacheManager:
    """Manages persistent caching of LLM macro consensus decisions."""

    def __init__(self, cache_file: Path | None = None, ttl_hours: float = 24.0) -> None:
        self.cache_file = cache_file or DEFAULT_CACHE_FILE
        self.ttl_hours = ttl_hours
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> CachedMacroDecision | None:
        """Load and return cached consensus if it exists and is within 24 hours."""
        if not self.cache_file.exists():
            return None

        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            cached = CachedMacroDecision(**data)
            if cached.is_valid():
                logger.info(
                    "✓ Loaded macro consensus from 24h cache (Regime: %s, %.1fh remaining). Zero LLM API calls needed.",
                    cached.regime,
                    cached.remaining_hours(),
                )
                return cached
            else:
                logger.info("Macro cache expired (> %.1f hours old). Refreshing via LLM...", self.ttl_hours)
                return None
        except Exception as e:
            logger.warning("Failed to read macro cache: %s", e)
            return None

    def save(
        self,
        regime: str,
        confidence: float,
        summary: str,
        debates: list[dict[str, Any]],
        headlines_count: int = 0,
    ) -> CachedMacroDecision:
        """Save fresh consensus decision with 24-hour expiration."""
        now = datetime.now(UTC)
        expires = now + timedelta(hours=self.ttl_hours)
        cached = CachedMacroDecision(
            cached_at=now.isoformat(),
            expires_at=expires.isoformat(),
            regime=regime,
            confidence=confidence,
            summary=summary,
            debates=debates,
            headlines_count=headlines_count,
        )
        try:
            self._ensure_dir()
            self.cache_file.write_text(json.dumps(asdict(cached), indent=2), encoding="utf-8")
            logger.info("Saved macro consensus to cache at %s (Valid for %.1f hours)", self.cache_file, self.ttl_hours)
        except Exception as e:
            logger.warning("Failed to write macro cache: %s", e)

        return cached

    def clear(self) -> None:
        """Invalidate the cache to force a fresh model call."""
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
                logger.info("Macro cache cleared.")
            except Exception:
                pass


# Global singleton cache
macro_cache = MacroCacheManager()
